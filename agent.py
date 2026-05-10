import json
import os
from typing import Any, Callable, Dict, List, Mapping, Optional
from loguru import logger

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from langchain_litellm import ChatLiteLLM

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from skills import (
    SKILLS,
    SkillResponseUnion,
    compare_variants,
    costliest_system,
    count_parts,
    count_unique_parts,
    heaviest_system,
    most_complex_system,
)

load_dotenv()

DEFAULT_OLLAMA_CHAT_MODEL = "llama3.1:8b"
DEFAULT_OPENAI_CHAT_MODEL = "gpt-4o-mini"

class RoutingDecision(BaseModel):
    use_tools: bool = Field(description="True if a BOM skill should run.")
    suggested_skill: Optional[str] = None
    suggested_parameters: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class ToolCallResult(BaseModel):
    name: str
    arguments: Dict[str, Any]
    result: SkillResponseUnion


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default

    s = raw.strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False

    logger.error(f"Boolean for {name} in environment is invalid: {raw}")
    raise ValueError(f"Invalid boolean for environment variable {name}: {raw}")


def _strip_fence(text: str) -> str:
    s = text.strip()
    if not s.startswith("```"):
        return s
    parts = s.split("```")
    inner = parts[1].lstrip() if len(parts) >= 2 else s
    if inner.lower().startswith("json"):
        inner = inner[4:].lstrip()
    return inner.strip()


def _extract_json_dict(text: str) -> Dict[str, Any]:
    cleaned = _strip_fence(text)
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object in model output")
    obj = json.loads(cleaned[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("Expected a JSON object")
    return obj


def _skill_schemas_json(tools_schema: List[Dict[str, Any]]) -> str:
    slim = [
        {"name": t["function"]["name"], "description": t["function"]["description"], "parameters": t["function"]["parameters"]}
        for t in tools_schema
    ]
    return json.dumps(slim, ensure_ascii=True)


class LangChainBOMAgent:

    OLLAMA_MODEL_KEY = "OLLAMA_MODEL"
    OLLAMA_HOST_KEY = "OLLAMA_HOST"
    OLLAMA_PORT_KEY = "OLLAMA_PORT"

    def __init__(self, model: Optional[str] = None):
        self.use_ollama = _env_bool(self.OLLAMA_MODEL_KEY, default=True)
        self.llm = self._create_chat_llm(model)

        self.tools_schema = self._build_tool_definitions()
        self.tool_llm = self.llm.bind_tools(self.tools_schema)

        self.skills: Mapping[str, Callable[..., Any]] = {
            "count_parts": count_parts,
            "count_unique_parts": count_unique_parts,
            "heaviest_system": heaviest_system,
            "costliest_system": costliest_system,
            "most_complex_system": most_complex_system,
            "compare_variants": compare_variants,
        }

    def _resolve_litellm_model_id(self, explicit: Optional[str]) -> str:
        if explicit and explicit.strip():
            m = explicit.strip()
        elif self.use_ollama:
            m = os.getenv("OLLAMA_CHAT_MODEL", DEFAULT_OLLAMA_CHAT_MODEL).strip()
        else:
            m = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_CHAT_MODEL).strip()

        if self.use_ollama:
            if not m.startswith("ollama/"):
                m = f"ollama/{m}"
            return m


        if m.startswith("ollama/"):
            logger.warning(
                "OLLAMA_MODEL is false but model id looks like Ollama ({}). "
                "Set OPENAI_MODEL or pass an OpenAI model id.",
                m,
            )
        return m

    def _create_chat_llm(self, model: Optional[str] = None) -> ChatLiteLLM:
        self.model_name = self._resolve_litellm_model_id(model)

        kwargs: Dict[str, Any] = {"model": self.model_name, "temperature": 0}
        if self.use_ollama:
            host = os.environ.get(self.OLLAMA_HOST_KEY, "127.0.0.1")
            port = os.environ.get(self.OLLAMA_PORT_KEY, "11434")
            kwargs["api_base"] = f"http://{host}:{port}".rstrip("/")

        return ChatLiteLLM(**kwargs)

    def _build_tool_definitions(self) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []

        PARAMETERS_KEY = "parameters"
        DESCRIPTION_KEY = "description"

        for name, info in SKILLS.items():
            params = info.get(PARAMETERS_KEY)
            if not isinstance(info, dict) or not isinstance(params, dict):
                logger.warning("Invalid skill info for %s. Skipping.", name)
                continue

            properties: Dict[str, Any] = {
                parameter_name: {
                    "type": parameter_info["type"],
                    "description": parameter_info["description"],
                    **({"enum": list(parameter_info["enum"])} if "enum" in parameter_info else {}),
                }
                for parameter_name, parameter_info in params.items()
            }
            required = [parameter_name for parameter_name, parameter_info in params.items() if parameter_info.get("required")]
            description = info.get(DESCRIPTION_KEY, f"Function to {name}")
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                        },
                    },
                }
            )

        logger.info(f"Built {len(tools)} tool definitions")
        return tools

    def _routing_prompt_text(self) -> str:
        schemas = _skill_schemas_json(self.tools_schema)
        return (
            "You are a routing gate for an automotive BOM query system.\n"
            "Respond with ONE JSON object only (no markdown, no extra text).\n"
            "Keys: use_tools (boolean), suggested_skill (string or null), "
            "suggested_parameters (object), reason (string).\n\n"
            f"Available skills:\n{schemas}"
        )
    
    def _synthesis_system_prompt(self) -> str:
        return (
            "You are a helpful engineering assistant for an automotive company.\n"
            "Answer based only on the data provided. Be precise about numbers.\n"
            "Mention the variant and system name in your answer.\n"
            "Answer in one or two sentences."
        )

    def route(self, query: str) -> RoutingDecision:
        prompt = ChatPromptTemplate.from_messages(
            [("system", "{system}"), ("human", "{query}")]
        )
        chain = prompt | self.llm | StrOutputParser()
        raw = chain.invoke({"system": self._routing_prompt_text(), "query": query})
        try:
            data = _extract_json_dict(raw)
            return RoutingDecision.model_validate(data)
        except Exception as first_exception:
            logger.warning("Routing JSON parse failed (first try): {}", first_exception)
            try:
                raw2 = chain.invoke(
                    {
                        "system": self._routing_prompt_text()
                        + "\n\nOutput ONLY valid JSON. No prose.",
                        "query": query,
                    }
                )
                data = _extract_json_dict(raw2)
                return RoutingDecision.model_validate(data)
            except Exception as second_exception:
                logger.warning(
                    "Routing JSON parse failed after retry; defaulting to direct chat: {}",
                    second_exception,
                )
                return RoutingDecision(
                    use_tools=False,
                    suggested_skill=None,
                    suggested_parameters={},
                    reason="Routing model did not return valid JSON; answering without BOM tools.",
                )

    def _tool_stage_system_prompt(self, decision: RoutingDecision) -> str:
        hint = json.dumps(
            {
                "suggested_skill": decision.suggested_skill,
                "suggested_parameters": decision.suggested_parameters,
                "gate_reason": decision.reason,
            },
            ensure_ascii=True,
        )
        return (
            "You are selecting a BOM skill. Emit exactly one tool call; no natural-language answer.\n"
            f"Prior routing suggestion (JSON): {hint}\n"
            "Prefer this suggestion when it fits; override if another skill is clearly better."
        )

    @staticmethod
    def _first_tool_call(msg: AIMessage) -> Optional[tuple[str, Dict[str, Any]]]:
        calls = getattr(msg, "tool_calls", None) or []
        if not calls:
            return None
        tc = calls[0]
        if isinstance(tc, dict):
            name = tc.get("name") or tc.get("function", {}).get("name")
            args = tc.get("args") or tc.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args)
            return str(name), dict(args)
        name = getattr(tc, "name", None) or getattr(tc, "function", {}).get("name")
        args = getattr(tc, "args", {}) or {}
        return str(name), dict(args)

    def run_skill(self, query: str, decision: RoutingDecision) -> ToolCallResult:
        messages = [
            SystemMessage(content=self._tool_stage_system_prompt(decision)),
            HumanMessage(content=query),
        ]
        
        ai: AIMessage = self.tool_llm.invoke(messages)
        parsed = self._first_tool_call(ai)
        
        if parsed:
            name, arguments = parsed
        elif decision.suggested_skill and decision.suggested_skill in self.skills:
            name, arguments = decision.suggested_skill, dict(decision.suggested_parameters or {})
        else:
            raise RuntimeError("No tool call and no usable routing suggestion.")

        if name not in self.skills:
            raise RuntimeError(f"Unknown skill: {name}")
        
        
        result = self.skills[name](**arguments)
        return ToolCallResult(name=name, arguments=arguments, result=result)


    @staticmethod
    def _result_to_jsonable(result: Any) -> Any:
        if hasattr(result, "model_dump"):
            return result.model_dump()
        return result

    def synthesize(self, query: str, skill_name: str, arguments: Dict[str, Any], result: Any) -> str:
        payload = json.dumps(
            [{"skill": skill_name, "parameters": arguments, "result": self._result_to_jsonable(result)}],
            ensure_ascii=True,
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self._synthesis_system_prompt()),
                ("human", "Question: {query}\nData from knowledge graph: {data}"),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        return chain.invoke({"query": query, "data": payload}).strip()

    def ask(self, query: str) -> str:
        decision = self.route(query)
        if not decision.use_tools:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", "You are a helpful assistant. Reply clearly and concisely."),
                    ("human", "{query}"),
                ]
            )
            chain = prompt | self.llm | StrOutputParser()
            return chain.invoke({"query": query}).strip()

        tc = self.run_skill(query, decision)
        return self.synthesize(query, tc.name, tc.arguments, tc.result)


if __name__ == "__main__":
    agent = LangChainBOMAgent()
    while True:
        user_input = input("\nAsk a BOM question (or 'quit'): ").strip()
        if user_input.lower() in {"quit", "exit"}:
            break
        print(agent.ask(user_input))

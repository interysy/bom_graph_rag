# Reflection

## 1. Ontology design decisions: Why did you model quantity the way you did (property on Part vs. reification)? What would break in your SPARQL queries if you had chosen the other approach?

I used reification to model `quantity` attribute on the `PartLink` entity. This means that an **Assembly** is connected to a **Part** via this intermediary model, which has the `bom:quantity` property on it. 

The reason behind this is that **Part**s are to be shared and appear with different quantities across unique Variants/Systems/Assemblies combinations. 

If `quantity` was an attribute on **Part** that was shared then e.g. Assembly of Sedan and Assembly of SUV would need to have the same `quantity` or would need to have unique part/duplicated URIs e.g. `part:m8bolt_sedan_engine` and `part:m8bolt_suv_engine`. In the first scenario our aggregation queries (e.g. SUM(?qty), SUM(?qty * weight), SUM(?qty * price)) would be wrong, while in the second scenario we would not be able to reuse parts, taking up more storage.


## 2. Graph RAG vs. Vector RAG: For this use case, why is a SPARQL-based retrieval approach superior to embedding the BOM into a vector store and using similarity search? Are there any query types where vector search would be better?

Bill of Materials data is hierarchical, as majority of entities have a parent and a child. For example Vehicle -> System -> Assembly -> Part.  

Due to the nature of the BOM data, tree/graph traversal needs to be undertaken to answer complex, multi-hop queries such as "How many parts in total are in the BOM for the SUV?"  that with a flat vector search would likely result in "hallucinations" or data loss. SPARQL lends itself nicely, as we can easily navigate along the edges of the graph, from the **Vehicle** (e.g. SUV) all the way to the **Part** with mathematical certainty.

If we used vector search we could probably find excerpts on the Vehicle and the Part, but lack the relational knowledge to understand that the **Part** is part of this **Vehicle** and at what quantity, unless this is explicitly mentioned.

Vector Search could be better when dealing with unstructured data, ambiguous queries, and discovery tasks that fall outside the rigid schema of a traditional Knowledge Graph - semantic queries such as "Which components in the drive assembly are most likely to cause a low-frequency humming noise?". This is because vector search can retrieve chunks from related documents and identify relevant paragraphs that explicitly mention the answer, providing context that is likely not captured in the graph (how would we model that there is a low-frequency humming noise on a specific Part)? 

## 3. Agent failure modes: Describe two scenarios where your agent would return a wrong or empty answer. How would you detect and handle them?

Main failures can come from routing and tool arguments. 

1. User language

The user might say "Hatchback", which needs to be modelled to "Hatch". We rely on the model to do this, if it does not happen and the model doesn't pass a valid name, a ValueError could be raised terminating the program. Alternatively the system_name could be omitted, giving the user the wrong response or a generic response with no tool call. 

To handle I could: 
* add a synonym map 
* more robust try/except around skill invocation
* a response to the user asking to clarify the query, while letting them know of the list of Variants and Syetsm


2. Double failure on JSON

If routing JSON is invalid twice, route() sets use_tools=False and the user gets a generic chat answer with no Fuseki data—looks “empty” or confidently wrong relative to the BOM.

To improve I should remove the silent fall to tbe generic chat, but return a reply letting the user know about a failure and suggest to ask a clarifying question.


## 4. Scaling: If this BOM had 50 variants and 500,000 unique parts, what would change in your data generation, storage, and query strategy?

1. **Data generation** would likely need to be batched to avoid memory overflows. We could also generate or load the data in parallel to speed up seeding. 

2. For the **Query Strategy** we could introduce something like "Named Graphs" to speed up traversal when there is 500,000 parts. Instead of having a global graph that would need to be traversed every time, we could load e.g. each variant into its own unique identifier graph when looking for answers on e.g. SUV. We could also cache popular queries to minimise processing time. 


## 5. One thing you would do differently if you had more time, and why.

Currently a ValueError is raised if the LLM passes an argument that `skills.py` cannot normalise (e.g. invalid `variant_code` or `system_name`), which can terminate the agent instead of returning a helpful reply. 

With more time I would catch errors at the skill boundary (as well as log them), return a clear explanation and suggested valid values (from the enums). I could also add a synonym layer for variant names before invocation—so the agent degrades gracefully instead of failing hard.
## Instructions to Update the Gradio App jupyter notebook

### First uodate the method search_and_answer to use LangChain and the new philatelic_rag_template with the enhanced prompt defined 
You must use the langchain for use the the llm defined in the setup of the notebook: 

llm = ChatOpenAI(
            model="gpt-5-nano", 
            api_key=OPENAI_API_KEY, 
            temperature=1,  # obligatorio para gpt-5-nano
            timeout=120.0,
            model_kwargs={
                "verbosity": "medium",
                "reasoning_effort" : "low"
            })


## Add the advance retrieval approach to the gradio interface
The idea is to first use the hybrid approach and in the same time use the compressed_docs = search_stamps_with_compression(
     query,
     client=client, 
     embeddings=embeddings, 
     limit = 50,
     llm=llm,
     alpha=0.30,  # 30% vectorial, 70% keywords para números exactos
     diversity_lambda=0.75)  # 75% relevancia, 25% diversidad ) 

This will take some time but I need to show both answers.

So your goal is to update my gradio app @gradio_app.ipynb to use langchain in the search_and_answer function and also use the retrieval prompt defined as philatelic_rag_template in all (the basic hybrid approach and the advance approach). Also to add to the gradio the new search_stamps_with_compression advance approach.

Both approach run in parallel. Maybe use a tab or something to distinct the two approach and show all the details (docs retrieved etc)

Important: All need to be in english, so you update the gradio interface to show all the texts in english.
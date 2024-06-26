import csv
import loguru
import re
from src.models.schemas.train import TrainFileIn
from datasets import load_dataset

from src.config.settings.const import UPLOAD_FILE_PATH, RAG_NUM, LOAD_BATCH_SIZE
from src.repository.ai_models import ai_model
from src.repository.rag.base import BaseRAGRepository
from src.repository.vector_database import vector_db
from src.repository.conversation import ConversationWithSession, conversations

class RAGChatModelRepository(BaseRAGRepository):
    async def load_model(self, session_id: int, model_name: str) -> bool:
        # Init model with input model_name
        try:
            ai_model.initialize_model(model_name)
            pass
        except Exception as e:
            loguru.logger.info(f"Exception --- {e}")
            return False
        return True

    def search_context(self, query, n_results=RAG_NUM):
        query_embeddings = ai_model.encode_string(query)
        loguru.logger.info(f"Embeddings Shape --- {query_embeddings.shape}")
        rag_res = vector_db.search(data=query_embeddings, n_results=n_results)
        rank = ai_model.cross_encoder.rank(query, rag_res)
        return rag_res[rank[0]['corpus_id']]

    async def get_response(self, session_id: int, input_msg: str, chat_repo) -> str:

        if session_id not in conversations:
            conversations[session_id] = ConversationWithSession(session_id, chat_repo)
            await conversations[session_id].load()
        con = conversations[session_id]
        con.conversation.add_message({"role": "user", "content": input_msg})
        context = self.search_context(input_msg)
        answer = ai_model.generate_answer(con,context)
        loguru.logger.info(f'ai generate_answer value:{answer}')
        # TODO stream output
        return answer

    async def load_csv_file(self, file_name: str, model_name: str) -> bool:
        # read file named file_name and convert the content into a list of strings @Aisuko
        loguru.logger.info(file_name)
        loguru.logger.info(model_name)
        data = []
        with open(UPLOAD_FILE_PATH + file_name, "r") as file:
            # Create a CSV reader
            reader = csv.reader(file)
            # Iterate over each row in the CSV
            for row in reader:
                # Add the row to the list
                data.extend(row)
        loguru.logger.info(f"load_csv_file data_row:{data}")
        embedding_list = ai_model.encode_string(data)
        vector_db.insert_list(embedding_list, data)

        return True

    def load_data_set(self, param: TrainFileIn)-> bool:
        loguru.logger.info(f"load_data_set param {param}")
        if param.directLoad:
            self.load_data_set_directly(param=param)
        elif param.embedField is None or param.resField is None:
            self.load_data_set_all_field(dataset_name=param.dataSet) 
        else:
            self.load_data_set_by_field(param=param)
        return True

    def load_data_set_directly(self, param: TrainFileIn)->bool:
        r"""
        If the data set is already in the form of embeddings, 
        this function can be used to load the data set directly into the vector database.
        
        @param param: the instance of TrainFileIn
        
        @return: boolean
        """
        reader_dataset=load_dataset(param.dataSet)
        resField = param.resField if param.resField else '0'
        collection_name = self.trim_collection_name(param.dataSet)
        vector_db.create_collection(collection_name = collection_name)
        loguru.logger.info(f"load_data_set_all_field dataset_name:{param.dataSet} into collection_name:{collection_name}")
        count = 0
        embed_field_list = []
        res_field_list = []
        for item in reader_dataset['train']:
         # check contail field
            # if resField not in item or embedField not in item :
            resField_val=item.get(resField, '')
            res_field_list.append(resField_val)
            embedField_val = [value for key, value in item.items() if key != resField]
            embed_field_list.append(embedField_val)
            count += 1
            if count % LOAD_BATCH_SIZE == 0:
                vector_db.insert_list(embed_field_list, res_field_list, collection_name,start_idx = count) 
                embed_field_list = []
                res_field_list = []
                loguru.logger.info(f"load_data_set_all_field count:{count}")
        vector_db.insert_list(embed_field_list, res_field_list, collection_name,start_idx = count)
        loguru.logger.info(f"load_data_set_all_field count:{count}")
        loguru.logger.info("Dataset loaded successfully")
        return True



    def load_data_set_all_field(self, dataset_name: str)-> bool:
        reader_dataset=load_dataset(dataset_name)
        collection_name = self.trim_collection_name(dataset_name)
        vector_db.create_collection(collection_name = collection_name)
        loguru.logger.info(f"load_data_set_all_field dataset_name:{dataset_name} into collection_name:{collection_name}")
        count = 0
        doc_list = []
        for item_dict in reader_dataset['train']:
            doc_str =''
            for key, value in item_dict.items():
                if(isinstance(key, type(value))):
                    doc_str += f" {key}:{value}"
            count += 1
            doc_list.append(doc_str)
            if count % LOAD_BATCH_SIZE == 0:
                embedding_list = ai_model.encode_string(doc_list)
                vector_db.insert_list(embedding_list, doc_list, self.trim_collection_name(dataset_name),start_idx = count)
                loguru.logger.info(f"load_data_set_all_field count:{count}")
                doc_list = []
        embedding_list = ai_model.encode_string(doc_list)
        vector_db.insert_list(embedding_list, doc_list, self.trim_collection_name(dataset_name),start_idx = count)
        loguru.logger.info(f"load_data_set_all_field count:{count}")
        loguru.logger.info("Dataset loaded successfully")
        return True

    def load_data_set_by_field(self, param: TrainFileIn)->bool:
        reader_dataset=load_dataset(param.dataSet)
        embedField=param.embedField
        resField= param.resField
        collection_name = self.trim_collection_name(param.dataSet)
        vector_db.create_collection(collection_name = collection_name)
        loguru.logger.info(f"load_data_set_all_field dataset_name:{param.dataSet} into collection_name:{collection_name}")
        count = 0
        embed_field_list = []
        res_field_list = []
        for item in reader_dataset['train']:
         # check contail field
            # if resField not in item or embedField not in item :
            embedField_val=item.get(embedField, '')
            resField_val=item.get(resField, '')
            embed_field_list.append(embedField_val)
            res_field_list.append(resField_val)
            count += 1
            if count % LOAD_BATCH_SIZE == 0:
                embedding_list = ai_model.encode_string(embed_field_list)
                vector_db.insert_list(embedding_list, res_field_list, collection_name,start_idx = count) 
                embed_field_list = []
                res_field_list = []
                loguru.logger.info(f"load_data_set_all_field count:{count}")
        embedding_list = ai_model.encode_string(embed_field_list)
        vector_db.insert_list(embedding_list, res_field_list, collection_name,start_idx = count)
        loguru.logger.info(f"load_data_set_all_field count:{count}")
        loguru.logger.info("Dataset loaded successfully")
        return True

    async def evaluate_response(self, request_msg: str, response_msg: str) -> float:
        evaluate_conbine=[request_msg, response_msg]
        score = ai_model.cross_encoder.predict(evaluate_conbine)
        return score

    def trim_collection_name(self, name: str) -> str:
        return re.sub(r'\W+', '', name)
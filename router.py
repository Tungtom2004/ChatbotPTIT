import numpy as np 

class SemanticRouter():
    def __init__(self,embedding,routes):
        self.routes = routes 
        self.embedding = embedding 
        self.routeEmbeddings = {}

        for route in self.routes:
            self.routeEmbeddings[route.name] = self.embedding.encode(route.samples)
        
    
    def get_routes(self):
        return self.routes 
    
    def guide(self,query):
        queryEmbedding = self.embedding.encode([query])
        queryEmbedding = queryEmbedding / np.linalg.norm(queryEmbedding)
        scores = []

        #Calculate the cosine similarity between the query and each route
        for route in self.routes:
            routesEmbedding = self.routeEmbeddings[route.name] / np.linalg.norm(self.routeEmbeddings[route.name])
            score = np.mean(np.dot(routesEmbedding,queryEmbedding.T).flatten())
            scores.append((score,route.name))
        
        scores.sort(reverse = True)
        return scores[0]

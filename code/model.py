"""
Created on Mar 1, 2020
Pytorch Implementation of LightGCN in
Xiangnan He et al. LightGCN: Simplifying and Powering Graph Convolution Network for Recommendation

@author: Jianbai Ye (gusye@mail.ustc.edu.cn)

Define models here
"""
import world
import torch
from dataloader import BasicDataset
from torch import nn
import numpy as np


class BasicModel(nn.Module):    
    def __init__(self):
        super(BasicModel, self).__init__()
    
    def getUsersRating(self, users):
        raise NotImplementedError
    
class PairWiseModel(BasicModel):
    def __init__(self):
        super(PairWiseModel, self).__init__()
    def bpr_loss(self, users, pos, neg):
        """
        Parameters:
            users: users list 
            pos: positive items for corresponding users
            neg: negative items for corresponding users
        Return:
            (log-loss, l2-loss)
        """
        raise NotImplementedError
    
class PureMF(BasicModel):
    def __init__(self, 
                 config:dict, 
                 dataset:BasicDataset):
        super(PureMF, self).__init__()
        self.num_users  = dataset.n_users
        self.num_items  = dataset.m_items
        self.latent_dim = config['latent_dim_rec']
        self.f = nn.Sigmoid()
        self.__init_weight()
        
    def __init_weight(self):
        self.embedding_user = torch.nn.Embedding(
            num_embeddings=self.num_users, embedding_dim=self.latent_dim)
        self.embedding_item = torch.nn.Embedding(
            num_embeddings=self.num_items, embedding_dim=self.latent_dim)
        print("using Normal distribution N(0,1) initialization for PureMF")
        
    def getUsersRating(self, users):
        users = users.long()
        users_emb = self.embedding_user(users)
        items_emb = self.embedding_item.weight
        scores = torch.matmul(users_emb, items_emb.t())
        return self.f(scores)
    
    def bpr_loss(self, users, pos, neg):
        users_emb = self.embedding_user(users.long())
        pos_emb   = self.embedding_item(pos.long())
        neg_emb   = self.embedding_item(neg.long())
        pos_scores= torch.sum(users_emb*pos_emb, dim=1)
        neg_scores= torch.sum(users_emb*neg_emb, dim=1)
        loss = torch.mean(nn.functional.softplus(neg_scores - pos_scores))
        reg_loss = (1/2)*(users_emb.norm(2).pow(2) + 
                          pos_emb.norm(2).pow(2) + 
                          neg_emb.norm(2).pow(2))/float(len(users))
        return loss, reg_loss
        
    def forward(self, users, items):
        users = users.long()
        items = items.long()
        users_emb = self.embedding_user(users)
        items_emb = self.embedding_item(items)
        scores = torch.sum(users_emb*items_emb, dim=1)
        return self.f(scores)

class LightGCN(BasicModel):
    def __init__(self, 
                 config:dict, 
                 dataset:BasicDataset):
        super(LightGCN, self).__init__()
        self.config = config
        self.dataset : dataloader.BasicDataset = dataset
        self.__init_weight()

    def __init_weight(self):
        self.num_users  = self.dataset.n_users
        self.num_items  = self.dataset.m_items
        self.latent_dim = self.config['latent_dim_rec']
        self.n_layers = self.config['lightGCN_n_layers']
        self.keep_prob = self.config['keep_prob']
        self.A_split = self.config['A_split']
        self.embedding_user = torch.nn.Embedding(
            num_embeddings=self.num_users, embedding_dim=self.latent_dim)
        self.embedding_item = torch.nn.Embedding(
            num_embeddings=self.num_items, embedding_dim=self.latent_dim)
        
        if world.config['outModel']=="1Linear":
            self.outModel=nn.Linear(3*self.latent_dim,1)
        elif world.config['outModel']=="2Linear":
            self.outModel=nn.Linear(self.latent_dim,1)
            self.outModel2=nn.Linear(3*self.latent_dim,self.latent_dim)
        elif world.config['outModel']=="3Linear":
            self.outModel=nn.Linear(self.latent_dim,1)
            self.outModel2=nn.Linear(self.latent_dim,self.latent_dim)
            self.outModel3=nn.Linear(3*self.latent_dim,self.latent_dim)

        if self.config['pretrain'] == 0:
#             nn.init.xavier_uniform_(self.embedding_user.weight, gain=1)
#             nn.init.xavier_uniform_(self.embedding_item.weight, gain=1)
#             print('use xavier initilizer')
# random normal init seems to be a better choice when lightGCN actually don't use any non-linear activation function
            nn.init.normal_(self.embedding_user.weight, std=0.1)
            nn.init.normal_(self.embedding_item.weight, std=0.1)
            if world.config['outModel']=="1Linear":
                nn.init.normal_(self.outModel.weight,std=0.1)
            elif world.config['outModel']=="2Linear":
                nn.init.normal_(self.outModel.weight,std=0.1)
                nn.init.normal_(self.outModel2.weight,std=0.1)
            elif world.config['outModel']=="3Linear":
                nn.init.normal_(self.outModel.weight,std=0.1)
                nn.init.normal_(self.outModel2.weight,std=0.1)
                nn.init.normal_(self.outModel3.weight,std=0.1)
            
            world.cprint('use NORMAL distribution initilizer')
        else:
            self.embedding_user.weight.data.copy_(torch.from_numpy(self.config['user_emb']))
            self.embedding_item.weight.data.copy_(torch.from_numpy(self.config['item_emb']))
            print('use pretarined data')
        self.f = nn.Sigmoid()
        self.Graph = self.dataset.getSparseGraph()
        print(f"lgn is already to go(dropout:{self.config['dropout']})")

        # print("save_txt")
    def __dropout_x(self, x, keep_prob):
        size = x.size()
        index = x.indices().t()
        values = x.values()
        random_index = torch.rand(len(values)) + keep_prob
        random_index = random_index.int().bool()
        index = index[random_index]
        values = values[random_index]/keep_prob
        g = torch.sparse.FloatTensor(index.t(), values, size)
        return g
    
    def __dropout(self, keep_prob):
        if self.A_split:
            graph = []
            for g in self.Graph:
                graph.append(self.__dropout_x(g, keep_prob))
        else:
            graph = self.__dropout_x(self.Graph, keep_prob)
        return graph
    
    def computer(self):
        """
        propagate methods for lightGCN
        """       
        users_emb = self.embedding_user.weight
        items_emb = self.embedding_item.weight
        all_emb = torch.cat([users_emb, items_emb])
        #   torch.split(all_emb , [self.num_users, self.num_items])
        embs = [all_emb]
        if self.config['dropout']:
            if self.training:
                print("droping")
                g_droped = self.__dropout(self.keep_prob)
            else:
                g_droped = self.Graph        
        else:
            g_droped = self.Graph    
        
        for layer in range(self.n_layers):
            if self.A_split:
                temp_emb = []
                for f in range(len(g_droped)):
                    temp_emb.append(torch.sparse.mm(g_droped[f], all_emb))
                side_emb = torch.cat(temp_emb, dim=0)
                all_emb = side_emb
            else:
                all_emb = torch.sparse.mm(g_droped, all_emb)
            embs.append(all_emb)
        embs = torch.stack(embs, dim=1)
        #print(embs.size())
        light_out = torch.mean(embs, dim=1)
        users, items = torch.split(light_out, [self.num_users, self.num_items])
        return users, items
    
    def getUsersRating(self, users):
        all_users, all_items = self.computer()
        users_emb = all_users[users.long()].detach()
        items_emb = all_items.detach()

        if world.config['outModel']=="dot":
            rating = self.f(torch.matmul(users_emb, items_emb.t()))
        else:
            rating=torch.zeros((users_emb.shape[0],items_emb.shape[0]))

            for u in range(users_emb.shape[0]):            
                vec=torch.cat([users_emb[u,:].repeat((items_emb.shape[0],1)),items_emb,torch.mul(users_emb[u,:], items_emb)],dim=1)

                if world.config['outModel']=="1Linear":
                    rating[u,:]=torch.sigmoid(self.outModel(vec))[:,0]
                elif world.config['outModel']=="2Linear":
                    rating[u,:]=torch.sigmoid(self.outModel(torch.sigmoid(self.outModel2(vec))))[:,0]
                elif world.config['outModel']=="3Linear":
                    rating[u,:]=torch.sigmoid(self.outModel(torch.sigmoid(self.outModel2(torch.sigmoid(self.outModel3(vec))))))[:,0]

        return rating
    
    def getEmbedding(self, users, pos_items, neg_items):
        all_users, all_items = self.computer()
        users_emb = all_users[users]
        pos_emb = all_items[pos_items]
        neg_emb = all_items[neg_items]
        users_emb_ego = self.embedding_user(users)
        pos_emb_ego = self.embedding_item(pos_items)
        neg_emb_ego = self.embedding_item(neg_items)
        return users_emb, pos_emb, neg_emb, users_emb_ego, pos_emb_ego, neg_emb_ego
    
    def bpr_loss(self, users, pos, neg):
        (users_emb, pos_emb, neg_emb, 
        userEmb0,  posEmb0, negEmb0) = self.getEmbedding(users.long(), pos.long(), neg.long())
        reg_loss = (1/2)*(userEmb0.norm(2).pow(2) + 
                         posEmb0.norm(2).pow(2)  +
                         negEmb0.norm(2).pow(2)
                         )/float(len(users))
        
        
        if world.config['outModel']=="dot":
            pos_scores = torch.mul(users_emb, pos_emb)
            pos_scores = torch.sum(pos_scores, dim=1)
            neg_scores = torch.mul(users_emb, neg_emb)
            neg_scores = torch.sum(neg_scores, dim=1)
        else:
            pos_vec=torch.cat([users_emb,pos_emb,torch.mul(users_emb, pos_emb)],dim=1)
            neg_vec=torch.cat([users_emb,neg_emb,torch.mul(users_emb, neg_emb)],dim=1)
            if world.config['outModel']=="1Linear":
                pos_scores=torch.sigmoid(self.outModel(pos_vec))
                neg_scores=torch.sigmoid(self.outModel(neg_vec))
                reg_loss+=1./2*(self.outModel.weight.norm(2).pow(2))/float(len(users))
            elif world.config['outModel']=="2Linear":
                pos_scores=torch.sigmoid(self.outModel(torch.sigmoid(self.outModel2(pos_vec))))
                neg_scores=torch.sigmoid(self.outModel(torch.sigmoid(self.outModel2(neg_vec))))
                reg_loss+=1./2*(self.outModel.weight.norm(2).pow(2))/float(len(users))
                reg_loss+=1./2*(self.outModel2.weight.norm(2).pow(2))/float(len(users))
            elif world.config['outModel']=="3Linear":
                pos_scores=torch.sigmoid(self.outModel(torch.sigmoid(self.outModel2(torch.sigmoid(self.outModel3(pos_vec))))))
                neg_scores=torch.sigmoid(self.outModel(torch.sigmoid(self.outModel2(torch.sigmoid(self.outModel3(neg_vec))))))
                reg_loss+=1./2*(self.outModel.weight.norm(2).pow(2))/float(len(users))
                reg_loss+=1./2*(self.outModel2.weight.norm(2).pow(2))/float(len(users))
                reg_loss+=1./2*(self.outModel3.weight.norm(2).pow(2))/float(len(users))

        loss = torch.mean(torch.nn.functional.softplus(neg_scores - pos_scores))
        
        return loss, reg_loss
       
    def forward(self, users, items):
        # compute embedding
        all_users, all_items = self.computer()
        # print('forward')
        #all_users, all_items = self.computer()
        users_emb = all_users[users]
        items_emb = all_items[items]
        inner_pro = torch.mul(users_emb, items_emb)
        print(users_emb.shape)
        print(items_emb.shape)
        print(inner_pro.shape)
        gamma     = torch.sum(inner_pro, dim=1)
        return gamma

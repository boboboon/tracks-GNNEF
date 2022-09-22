# -*- coding: utf-8 -*-
"""GNN_Track.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1WOHqy7-il36fS2CYL9jSBs4KoGs0k85E
"""

import torch
def format_pytorch_version(version):
  return version.split('+')[0]

TORCH_version = torch.__version__
TORCH = format_pytorch_version(TORCH_version)

def format_cuda_version(version):
  return 'cu' + version.replace('.', '')

CUDA_version = torch.version.cuda
CUDA = format_cuda_version(CUDA_version)

!pip install torch-scatter     -f https://pytorch-geometric.com/whl/torch-{TORCH}+{CUDA}.html
!pip install torch-sparse      -f https://pytorch-geometric.com/whl/torch-{TORCH}+{CUDA}.html
!pip install torch-cluster     -f https://pytorch-geometric.com/whl/torch-{TORCH}+{CUDA}.html
!pip install torch-spline-conv -f https://pytorch-geometric.com/whl/torch-{TORCH}+{CUDA}.html
!pip install torch-geometric

import numpy as np 
import pandas as pd
import time
import os
import itertools 
import matplotlib.pyplot as plt

from torch_geometric.data import Data, Dataset#,DataLoader
from torch_geometric.loader import DataLoader
from torch import Tensor
import torch.nn as nn
import torch.optim as optim

import torch.nn.functional as F
import torch_geometric.transforms as Tr
from torch_geometric.nn import MessagePassing
from torch_geometric.utils import to_networkx
from torch.nn import Sequential as Seq, Linear, ReLU, Sigmoid
from torch.optim.lr_scheduler import StepLR

from collections import namedtuple

"""Create Dataset and Dataloader"""

class GraphDataset(Dataset):
    def __init__(self,graph_files,file_name,transform=None, pre_transform=None):
        super(GraphDataset,self).__init__()

        self.graph_files = graph_files
        self.file_name = file_name
    
    @property                 
    def raw_file_names(self):
        return self.graph_files

    @property
    def processed_file_names(self):
        return []

   
        
    def get(self, idx):
          
          data = torch.load(f'/PATH_TO_FILES/{self.file_name}' + f'data_{idx}.pt')
      
          
          return data    
          
    def len(self):
          
          return len(self.graph_files)

#READ FILES 
home_dir = "../"   
test ='GRAPH_FINAL_TEST_MASTER/'
indir = '/PATH_TO_FILES/'
    
graph_files_test = np.array(os.listdir(indir + test))
graph_files_test = [os.path.join(indir+test,file)
                           for file in graph_files_test]
test_set = GraphDataset(graph_files_test, test)

"""## Arquitecture """

class RelationalModel(nn.Module):
    def __init__(self, input_size, output_size, hidden_size):
        super(RelationalModel, self).__init__()
        
        self.layers = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, output_size),
        )

    def forward(self, m):
        return self.layers(m)

class ObjectModel(nn.Module):
    def __init__(self, input_size, output_size, hidden_size):
        super(ObjectModel, self).__init__()
        
        self.layers = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, output_size),
        )

    def forward(self, C):
        return self.layers(C)


class InteractionNetwork(MessagePassing):
    def __init__(self, node_f_size, edge_attr_size,message_out, update_out, hidden_size):
        super(InteractionNetwork, self).__init__(aggr='add', 
                                                 flow='source_to_target')
        self.R1 = RelationalModel(2*node_f_size + edge_attr_size, message_out, hidden_size)    # 19 is the node_features * 2 + edge atributes output 4 
        self.O = ObjectModel(node_f_size + message_out, update_out, hidden_size)    # 10 is node features + output R1
        self.R2 = RelationalModel(2*update_out + message_out , 1, hidden_size)  #10 is from 2* output O + output R1(from the concat) 
        self.E: Tensor = Tensor()

    def forward(self, x: Tensor, edge_index: Tensor, edge_attr: Tensor) -> Tensor:
        x_tilde = self.propagate(edge_index, x=x, edge_attr=edge_attr, size=None)
        m2 = torch.cat([x_tilde[edge_index[1]],
                        x_tilde[edge_index[0]],
                        self.E], dim=1)
        return torch.sigmoid(self.R2(m2))
        
    def message(self, x_i, x_j, edge_attr):
        m1 = torch.cat([x_i, x_j, edge_attr], dim=1)
        self.E = self.R1(m1)
        return self.E

    def update(self, aggr_out, x):
        c = torch.cat([x, aggr_out], dim=1)
        return self.O(c)

#define the size of layers on the nn 
hidden_l_size = 16   #tunable parameter
message_out = 4       #tunable parameter
update_out = 3        #tunable parameter
edge_attr_size = 7
node_f_size = 6
#initialize model 
model = InteractionNetwork(node_f_size = node_f_size, edge_attr_size = edge_attr_size,message_out = message_out, update_out= update_out,hidden_size = hidden_l_size).to(device)

def binary_acc(y_pred, y_test,thld):
  """
  returns accuracy based on a given treshold
  """

  # true positives edges with ouput prediction bigger than thld(1) and label = 1
  TP = torch.sum((y_test==1.).squeeze() & 
                           (y_pred>thld).squeeze()).item()
  # true negatives edges with ouput prediction smaller than thld(0) and label = 0
  TN = torch.sum((y_test==0.).squeeze() & 
                           (y_pred<thld).squeeze()).item()
  # False positives edges with ouput prediction bigger than thld(1) and label = 0
  FP = torch.sum((y_test==0.).squeeze() & 
                           (y_pred>thld).squeeze()).item()
  # False negatives edges with ouput prediction smaller than thld(0) and label = 1                     
  FN = torch.sum((y_test==1.).squeeze() & 
                           (y_pred<thld).squeeze()).item() 
  #how many correct predictions are made, if FP = 0 and FN = 0 acc = 1                       
  acc = (TP+TN)/(TP+TN+FP+FN)
    
  return acc

#LOAD MODEL
model.load_state_dict(torch.load( '/PATH_TO_MODELS/model_master.pt',map_location=torch.device('cpu')))

"""## Predict segment"""

#TEST SECTION
def test_tracks(model, device, file_num, thld=0.5):
    model.eval()
    test_t0 = time.time()
    losses, accs = [], []
    outputs = []
    indeces = []
    y_list = []
    
    with torch.no_grad():
      #for batch_idx, data in enumerate(test_loader):
      data = test_set.get(file_num).to(device)
      output = model(data.x, data.edge_index, data.edge_attr)
      acc = binary_acc(y_pred = output, y_test = data.y, thld =  thld)
      loss = F.binary_cross_entropy(output.squeeze(1), data.y, 
                                          reduction='mean').item()
      # accs.append(acc)
      losses.append(loss)
      outputs.append(output)
      indeces.append(data.edge_index)
      y_list.append(data.y)
            #print(f"acc={TP+TN}/{TP+TN+FP+FN}={acc}")
    times = (time.time()-test_t0)
    #when batching works change acc for mean accs
    # print(f"...testing time: {time.time()-test_t0}s")
    #print(f'.............mean test loss={np.mean(losses):.6f}.....test  loss={loss:.6f}......test acc ={acc:.6f}\n')
    # print(f'.............mean test loss={np.mean(losses):.6f}......test acc ={acc:.6f}\n')
    return outputs, indeces, y_list, acc,times

############################### Predict segment##########
event = 10
thld = .493
pred, edge_list, y_list, accs, times = test_tracks(model, device, event, thld=thld)

"""## Build tracks"""

###################list of predicted segment and true segments##########
pred_test = pred[0].cpu().numpy()
#send edge list to cpu and transpose
edge_list_test = edge_list[0].cpu().numpy().T
#get the index of the prediction where pred is bigger than thld
pred_test.flatten()
pred_segments_idx = np.where(pred_test.flatten()>thld)[0]
true_segments_idx = np.where(y_list[0].cpu().numpy()==1)
#get the edge list pair where index = true_segments
pred_segments = edge_list_test[pred_segments_idx]
true_segments = edge_list_test[true_segments_idx]

def construct_graph(ids_array): 
  """Takes a list of edges and construct a track"""
  
  segment = ids_array.copy()
  graphs = []
  while len(segment) > 0:
    segment_list =[]
    no_more_conn = []
    for elem in segment:
      idx = np.where(ids_array[:,0] == elem[-1])
      connections = ids_array[idx]
      if len(connections) > 0:
        for conenction in connections:
          segment_list.append(np.unique(np.concatenate((elem,conenction))))
      else:
        no_more_conn.append(elem)
      
      segment = np.array(segment_list)
    graphs.append(np.array(no_more_conn))
  
  return graphs

##############show track accuracy####################
def track_accuracy(pred_track, truth_track):
  truths = []
  for i in range(len(pred_track)):
    for j in range (len(truth_track)):
      is_a_track = np.array_equal(pred_track[i] , truth_track[j], equal_nan=False)
      if is_a_track:
        truths.append(i)
        
  acc = len(truths)/ len(truth_track)
  return acc, truths

accuracies = np.zeros(len(pred_tracks))
correct_idx  = []
predicted = np.zeros(len(pred_tracks))
truth = np.zeros(len(pred_tracks))
edge = np.zeros(len(pred_tracks))
correct = np.zeros(len(pred_tracks))
for i in range(len(pred_tracks)):
  predicted[i] = len(pred_tracks[i])
  truth[i] = len(true_tracks[i])
  edge[i] = i + 1
  acc, truths = track_accuracy(pred_tracks[i], true_tracks[i])
  
  correct[i] = len(truths)
  accuracies[i] = acc  
  correct_idx.append(truths)
# print(accuracies)

acc_df = pd.DataFrame({'Ammount_hits':(edge[2:]+1).astype(int),'Ammount_edges': edge[2:].astype(int),
                       'Amount_predicted':predicted[2:].astype(int),'Correct_predicted' : correct[2:].astype(int),'Ammout_truth':truth[2:].astype(int),'Accuracy':accuracies[2:]})
acc_df
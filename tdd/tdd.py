from __future__ import annotations
from typing import Iterable, Sequence, Tuple, List, Any, Union, cast
import numpy as np
import torch

from . import CUDAcpl, weighted_node
from .CUDAcpl import _U_, CUDAcpl_Tensor, CUDAcpl2np
from . import node
from .node import  TERMINAL_ID, Node, IndexOrder, order_inverse
from .weighted_node import isequal, to_CUDAcpl_Tensor

import copy


from graphviz import Digraph
from IPython.display import Image



class TDD:
    '''
        TDD  functions as the compact representation of tensors,
        and can fit into tensor networks.
    '''
    def __init__(self, 
                    weights: CUDAcpl_Tensor,
                    data_shape: List[int],
                    node: Node|None,
                    index_order: IndexOrder = []):
        self.weights: CUDAcpl_Tensor = weights
        self.data_shape: List[int] = data_shape  #the data index shape (of the tensor it represents)
        self.node: Node|None = node

        '''
            index_order: how the inner index are mapped to outer representations
            for example, tdd[a,b,c] under index_order=[0,2,1] returns the value tdd[a,c,b]
            index_order == None means the trival index mapping [0,1,2,(...)]
        '''
        self.index_order: IndexOrder = index_order

    @property
    def dim_data(self) -> int:
        return len(self.data_shape)

    @property
    def parallel_shape(self) -> List[int]:
        return list(self.weights.shape[:-1])

    @property
    def global_order(self)-> List[int]:
        '''
            Return the index order containing both parallel and data indices.
            Note that the last index reserved for CUDA complex is not included
        '''
        parallel_index_order = [i for i in range(len(self.parallel_shape))]
        increment = len(self.parallel_shape)
        return parallel_index_order + [order+increment for order in self.index_order]
    
    @property
    def global_shape(self)-> List[int]:
        return self.parallel_shape + self.data_shape

    def __eq__(self, other: TDD) -> bool:
        '''
            Now this equality check only deals with TDDs with the same index order.
        '''
        res = self.index_order==other.index_order \
            and isequal((self.node,self.weights),(other.node,other.weights))
        return res

    def __str__(self):
        return str(self.numpy())


    @staticmethod
    def __as_tensor_iterate(tensor : CUDAcpl_Tensor, 
                    parallel_shape: List[int],
                    data_shape: List[int],
                    index_order: List[int], depth: int) -> TDD:
        '''
            The inner interation for as_tensor.

            tensor: will be referred to without cloning
            depth: current iteration depth, used to indicate index_order and termination
            index_order should not be []

            Guarantee: parallel_shape and index_order will not be modified.
        '''

        #checks whether the tensor is reduced to the [[...[val]...]] form
        if depth == len(data_shape):

            #maybe some improvement is needed here.
            if len(data_shape)==0:
                weights = tensor
            else:
                weights = (tensor[...,0:1,:]).view(parallel_shape+[2])
            res = TDD(weights,[],None,[])
            return res
        

        split_pos=index_order[depth]
        split_tensor = list(tensor.split(1,-len(data_shape)+split_pos-1))
            #-1 is because the extra inner dim for real and imag

        the_successors: List[TDD] =[]

        for k in range(data_shape[split_pos]):
            res = TDD.__as_tensor_iterate(split_tensor[k],parallel_shape,data_shape,index_order,depth+1)
            the_successors.append(res)

        #stack the sub-tdd
        succ_nodes = [item.node for item in the_successors]
        out_weights = torch.stack([item.weights for item in the_successors])
        temp_node = Node(0, depth, out_weights, succ_nodes)
        dangle_weights = CUDAcpl.ones(out_weights.shape[1:-1])
        #normalize at this depth
        new_node, new_dangle_weights = weighted_node.normalize((temp_node, dangle_weights), False)
        tdd = TDD(new_dangle_weights, [], new_node, [])

        return tdd


    @staticmethod
    def as_tensor(data : TDD|CUDAcpl_Tensor|np.ndarray|Tuple) -> TDD:
        '''
        construct the tdd tensor

        tensor:
            0. in the form of a TDD, then return a copy of it.
            1. in the form of a matrix only: assume the parallel index and index order to be []
            2. in the form of a tuple (data, index_shape, index_order)
            Note that if the input matrix is a torch tensor, 
                    then it must be already in CUDAcpl_Tensor(CUDA complex) form.
        '''
        if isinstance(data,TDD):
            return data.clone()

        if isinstance(data,Tuple):
            tensor,parallel_shape,index_order = data
        else:
            tensor = data
            parallel_shape = []
            index_order: List[int] = []
            
        if isinstance(tensor,np.ndarray):
            tensor = CUDAcpl.np2CUDAcpl(tensor)

        #pre-process above

        data_shape = list(tensor.shape[len(parallel_shape):-1])  #the data index shape
        if index_order == []:
            result_index_order = list(range(len(data_shape)))
        else:
            result_index_order = index_order.copy()


        if len(data_shape)!=len(result_index_order):
            raise Exception('The number of indices must match that provided by tensor.')

        '''
            This extra layer is also for copying the input list and pre-process.
        '''
        res = TDD.__as_tensor_iterate(tensor,parallel_shape,data_shape,result_index_order,0)

        
        res.index_order = result_index_order
        res.data_shape = data_shape
        return res

    
            
    def CUDAcpl(self) -> CUDAcpl_Tensor:
        '''
            Transform this tensor to a CUDA complex and return.
        '''
        trival_ordered_data_shape = [self.data_shape[i] for i in order_inverse(self.index_order)]
        node_data = to_CUDAcpl_Tensor((self.node,self.weights),trival_ordered_data_shape)
        
        #permute to the right index order
        node_data = node_data.permute(tuple(self.global_order+[node_data.dim()-1]))

        return node_data
        

    def numpy(self) -> np.ndarray:
        '''
            Transform this tensor to a numpy ndarry and return.
        '''
        return CUDAcpl2np(self.CUDAcpl())


    def clone(self) -> TDD:
        return TDD(self.weights.clone(), self.data_shape.copy(), self.node, self.index_order.copy())

        '''
    
    def __getitem__(self, key) -> TDD:
        Index on the data dimensions.

        Note that only limited form of indexing is allowed here.
        if not isinstance(key, int):
            raise Exception('Indexing form not supported.')
        
        # index by a integer
        inner_index = self.index_order.index(key) #get the corresponding index inside tdd
        node = self.node.
        '''
    

    def __index_reduce_proc(self, reduced_indices: List[int])-> Tuple[List[int], List[int]]:
        '''
            Return the data_shape and index_order after the reduction of specified indices.
            reduced_indices: corresponds to inner data indices, not the indices of tensor it represents.
            Note: Indices are counted in data indices only.
        '''
        new_data_shape = []
        indexed_index_order = []
        for i in range(len(self.data_shape)):
            if i not in reduced_indices:
                new_data_shape.append(self.data_shape[i])
                indexed_index_order.append(self.index_order[i])        
        new_index_order = sorted(range(len(indexed_index_order)), key = lambda k:indexed_index_order[k])

        return new_data_shape, new_index_order

    
    def index(self, data_indices: List[Tuple[int,int]]) -> TDD:
        '''
        Return the indexed tdd according to the chosen keys at given indices.
        Note: Indices should be count in the data indices only.

        Note: indexing acts on the data indices.

        indices: [(index1, key1), (index2, key2), ...]
        '''
        #transform to inner indices
        reversed_order = order_inverse(self.index_order)
        inner_indices = [(reversed_order[item[0]],item[1]) for item in data_indices]

        #get the indexing of inner data
        new_node, new_dangle_weights = weighted_node.index((self.node, self.weights), inner_indices)
        
        #process the data_shape and the index_order
        indexed_indices = []
        for pair in inner_indices:
            indexed_indices.append(pair[0])
        new_data_shape, new_index_order = self.__index_reduce_proc(indexed_indices)

        return TDD(new_dangle_weights, new_data_shape, new_node, new_index_order)

    @staticmethod
    def sum(a: TDD, b: TDD) -> TDD:
        '''
            Sum up tdd a and b, and return the reduced result. 
        '''

        new_node, new_weights = weighted_node.sum((a.node, a.weights), (b.node, b.weights))

        return TDD(new_weights, a.data_shape.copy(), new_node, a.index_order.copy())

    def contract(self, data_indices: Sequence[List[int]]) -> TDD:
        '''
            Contract the tdd according to the specified data_indices. Return the reduced result.
            data_indices should be counted in the data indices only.
            e.g. ([a,b,c],[d,e,f]) means contracting indices a-d, b-e, c-f (of course two lists should be in the same size)
        '''
        #transform to inner indices
        reversed_order = order_inverse(self.index_order)
        inner_indices = [(reversed_order[data_indices[0][k]],
                            reversed_order[data_indices[1][k]])
                            for k in range(len(data_indices[0]))]

        res_node, res_weights = self.node, self.weights

        #prevent the shared reference to weights
        if inner_indices == []:
            res_weights = self.weights.clone()

        inner_indices_copy = inner_indices.copy()
        while inner_indices != []:
            item = inner_indices[0]
            #get the index width, index it, and sum over it. Fairly Simple.
            index_width = self.data_shape[self.index_order[item[0]]]

            current_indices = [(item[0],0),(item[1],0)]
            summed_node, summed_weights = weighted_node.index((res_node, res_weights),current_indices)
            for i in range(1,index_width):
                current_indices = [(item[0],i),(item[1],i)]
                new_node, new_weights = weighted_node.index((res_node, res_weights),current_indices)
                summed_node, summed_weights = weighted_node.sum((summed_node, summed_weights), (new_node, new_weights))
            
            #update the result, adjust the indices
            res_node, res_weights = summed_node, summed_weights
            inner_indices = inner_indices[1:]
            for i in range(len(inner_indices)):
                i0, i1 = inner_indices[i][0], inner_indices[i][1]
                if i0 > item[0]:
                    i0 -= 1
                if i0 > item[1]:
                    i0 -= 1
                if i1 > item[0]:
                    i1 -= 1
                if i1 > item[1]:
                    i1 -= 1
                inner_indices[i] = (i0, i1)
        
        #process data_shape and index_shape
        reduced_indices = ()
        for pair in inner_indices_copy:
            reduced_indices += pair
        reduced_indices = list(reduced_indices)
        new_data_shape, new_index_order = self.__index_reduce_proc(reduced_indices)

        return TDD(res_weights, new_data_shape, res_node, new_index_order)





    def show(self, path: str='output', real_label: bool=True, full_output: bool = False, precision: int = 2):
        '''
            full_output: if True, then the edge will appear as a tensor, not the parallel index shape.

            (NO TYPING SYSTEM VERIFICATION)
        '''
        edge=[]              
        dot=Digraph(name='reduced_tree')
        dot=Node.layout(self.node,self.parallel_shape,self.index_order, dot,edge, real_label, full_output)
        dot.node('-0','',shape='none')

        if self.node == None:
            id_str = str(TERMINAL_ID)
        else:
            id_str = str(self.node.id)

        if list(self.weights.shape)==[2]:
            dot.edge('-0',id_str,color="blue",label=
                str(complex(round(self.weights[0].cpu().item(),precision),round(self.weights[1].cpu().item(),precision))))
        else:
            if full_output == True:
                label = str(CUDAcpl2np(self.weights))
            else:
                label =str(self.parallel_shape)
            dot.edge('-0',id_str,color="blue",label = label)
        dot.format = 'png'
        return Image(dot.render(path))


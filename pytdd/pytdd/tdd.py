
from __future__ import annotations
from typing import Any, Dict, Tuple, List, Union, Sequence;
import numpy as np
from . import CUDAcpl;
from .CUDAcpl import CUDAcpl_Tensor, CUDAcpl2np

# the C++ package
from . import ctdd

# the TDD index node
from .node import Node

# order coordinators
from .abstract_coordinator import AbstractCoordinator, OrderInfo
from .trival_coordinator import TrivalCoordinator
from .global_order_coordinator import GlobalOrderCoordinator

# for tdd graphing
from graphviz import Digraph
from IPython.display import Image


class TDD:
    coordinator_factory = {
        'trival': TrivalCoordinator(),
        'global_order': GlobalOrderCoordinator()
        }

    coordinator : AbstractCoordinator = coordinator_factory['global_order']
    #coordinator : AbstractCoordinator = coordinator_factory['trival']

    @staticmethod
    def set_coordinator(name) -> None:
        TDD.coordinator = TDD.coordinator_factory[name]

    def __init__(self, pointer, coordinator_info: OrderInfo):
        self._pointer : int = pointer
        self._info = ctdd.get_tdd_info(self._pointer)

        # here copy is not needed, because coordinator_info will only be resigned, not modified.
        self._coordinator_info: OrderInfo = coordinator_info

    @property
    def pointer(self) -> int:
        return self._pointer

    @property
    def coordinator_info(self) -> OrderInfo:
        return self._coordinator_info

    @property
    def node(self) -> Node:
        return Node(self._info["node"])

    @property
    def info(self) -> Dict:
        return self._info

    @property
    def shape(self) -> Tuple:
        return self._info["data shape"]
    
    @property
    def parallel_shape(self) -> Tuple:
        return self._info["parallel shape"]

    @property
    def storage_order(self) -> Tuple:
        return self._info["storage order"]

    # extremely time costy
    def size(self) -> int:
        return ctdd.get_tdd_size(self._pointer)

    def CUDAcpl(self) -> CUDAcpl_Tensor:
        return ctdd.to_CUDAcpl(self._pointer)

    def numpy(self) -> np.ndarray:
        return CUDAcpl.CUDAcpl2np(ctdd.to_CUDAcpl(self._pointer))

    def __str__(self):
        return str(self.numpy())


    def show(self, path: str='output', full_output: bool=False, precision: int=2):
        '''
            full_output: if True, then the edge will appear as a tensor, not the parallel index shape.
        '''
        edge=[]              
        tdd_node = self.node

        dot=Digraph(name='reduced_tree')
        dot=tdd_node.layout(self.storage_order, self.parallel_shape, dot, edge, full_output,precision)
        dot.node('-0','',shape='none')

        if tdd_node.pointer == 0:
            id_str = str(TERMINAL_ID)
        else:
            id_str = str(tdd_node.id)

        tdd_weight = self.info["weight"]
        if self.info["dim parallel"]==0:
            label= str(complex(round(tdd_weight[0].cpu().item(),precision),round(tdd_weight[1].cpu().item(),precision)))
        else:
            if full_output == True:
                label = str(CUDAcpl2np(tdd_weight))
            else:
                label =str(self.parallel_shape)
        dot.edge('-0',id_str,color="blue",label = label + " shape: " +str(self.shape))
        dot.format = 'png'
        return Image(dot.render(path))


    def __del__(self):
        if ctdd:
            if ctdd.delete_tdd:
                ctdd.delete_tdd(self._pointer)


    # the tensor methods

    @staticmethod
    def as_tensor(data : TDD|
                  Tuple[
                      CUDAcpl_Tensor|np.ndarray|Tuple[CUDAcpl_Tensor|np.ndarray, int, Sequence[int]],
                      Any
                  ]) -> TDD:

        '''
        construct the tdd tensor

        data:
            0. in the form of a TDD, then return a copy of it.
            1. in the form of (tensor, coordinator_info), where tensor is
                1a. in the form of a matrix only: assume the parallel_index_num to be 0, and index order to be []
                1b. in the form of a tuple (data, index_shape, index_order)
                Note that if the input matrix is a torch tensor, 
                        then it must be already in CUDAcpl_Tensor(CUDA complex) form.

        '''

        # pre-process
        if isinstance(data, TDD):
            # note the order information is also copied
            return TDD(ctdd.as_tensor_clone(data.pointer), data._coordinator_info);

        #extract the order_information
        data, coordinator_info = data
        coordinator_info = TDD.coordinator.create_order_info(coordinator_info)

        if isinstance(data,Tuple):
            tensor,parallel_i_num,storage_order = data
        else:
            tensor = data
            parallel_i_num = 0
            storage_order = []

        # if storage order not given, the coordinator will take over
        if storage_order == []:
            storage_order = TDD.coordinator.as_tensor_order(coordinator_info)
        else:
            storage_order = list(storage_order)
            
        if isinstance(tensor,np.ndarray):
            tensor = CUDAcpl.np2CUDAcpl(tensor)


        # examination

        data_shape = list(tensor.shape[parallel_i_num:-1])

        if len(data_shape)!=len(storage_order) and len(storage_order)!=0:
            raise Exception('The number of indices must match that provided by tensor.')

        pointer = ctdd.as_tensor(tensor, parallel_i_num, storage_order)

        return TDD(pointer, coordinator_info)


    @staticmethod
    def trace(tensor: TDD, axes:Sequence[Sequence[int]]) -> TDD:
        '''
            Trace the TDD at given indices.
        '''
        # examination
        if len(axes[0]) != len(axes[1]):
            raise Exception("The indices given by parameter axes does not match.")

        pointer = ctdd.trace(tensor.pointer, axes[0], axes[1])
        return TDD(pointer, TDD.coordinator.trace_order_info(tensor._coordinator_info, axes))


    @staticmethod
    def tensordot(a: TDD, b: TDD, 
                  axes: int|Sequence[Sequence[int]], rearrangement: Sequence[bool] = []) -> TDD:
        
        '''
            The pytorch-like tensordot method. Note that indices should be counted with data indices only.
            rearrangement: If not [], then will rearrange according to the parameter. Otherwise, it will rearrange according to the coordinator.
            parallel_tensor: Whether to tensor on the parallel indices.
        '''
        if rearrangement == []:
            rearrangement = TDD.coordinator.tensordot_rearrangement(a._coordinator_info, b._coordinator_info, axes)

        new_coordinator_info = TDD.coordinator.tensordot_order_info(a._coordinator_info, b._coordinator_info, axes)
        if isinstance(axes, int):
            pointer = ctdd.tensordot_num(a.pointer, b.pointer, axes, rearrangement)
        else:
            i1 = list(axes[0])
            i2 = list(axes[1])
            if len(i1) != len(i2):
                raise Exception("The list of indices provided")
            
            pointer = ctdd.tensordot_ls(a.pointer, b.pointer, i1, i2, rearrangement)
        
        res = TDD(pointer, new_coordinator_info)
        return res


    @staticmethod
    def permute(tensor: TDD, perm: Sequence[int]) -> TDD:
        return TDD(ctdd.permute(tensor.pointer, list(perm)),
                   TDD.coordinator.permute_order_info(tensor._coordinator_info, perm));
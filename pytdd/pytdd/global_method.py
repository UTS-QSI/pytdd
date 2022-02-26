from . import ctdd

def reset(device_cuda: bool):
    if device_cuda:
        ctdd.reset(1)
    else:
        ctdd.reset(0)

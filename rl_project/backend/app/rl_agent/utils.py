import random
import numpy as np
import torch


def set_seed(seed=42):
    """
    Set random seed for reproducibility.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def to_tensor(array):
    """
    Convert a numpy array to a torch tensor.
    """
    return torch.FloatTensor(array)


def save_model(model, path):
    """
    Save a PyTorch model.
    """
    torch.save(model.state_dict(), path)


def load_model(model, path):
    """
    Load a PyTorch model.
    """
    model.load_state_dict(torch.load(path))
    model.eval()


if __name__ == "_main_":
    set_seed(42)
    print("Utilities loaded successfully.")
# Reinforcement Learning Agent

## Overview

This module implements the intelligent decision-making component of the SOAR platform using Reinforcement Learning.

The agent learns to select the most appropriate action based on the current security alert state.

---

# Implemented Algorithms

## DQN (Deep Q-Network)

The DQN agent estimates Q-values for each possible action using a neural network.

Main features:

- Replay Buffer
- Epsilon-Greedy Exploration
- Neural Network approximation
- Model checkpoint saving

---

## PPO (Proximal Policy Optimization)

The PPO agent is based on the Actor-Critic architecture.

Main features:

- Actor Network
- Critic Network
- Policy Gradient Optimization
- Clipped Objective Function (simplified version)

---

# Project Structure

```
rl_agent/

│── dqn.py
│── ppo.py
│── networks.py
│── memory.py
│── policy.py
│── trainer.py
│── evaluator.py
│── inference.py
│── checkpoint.py
│── metrics.py
│── utils.py
```

---

# Training

Training is performed using:

```
python backend/app/rl_agent/trainer.py
```

---

# Testing

Run unit tests:

```
python -m backend.app.tests.test_networks

python -m backend.app.tests.test_dqn

python -m backend.app.tests.test_ppo
```

---

# Metrics

Training metrics include:

- Episode
- Reward
- Average Reward
- Loss
- Epsilon

Metrics are saved in:

```
logs/training_metrics.csv
```

---

# Model Checkpoints

The trained model checkpoints are stored in:

```
models/checkpoints/
```

---

# Future Improvements

- Double DQN
- Generalized Advantage Estimation (GAE)
- Entropy Bonus
- TensorBoard Integration
- Environment Integration
- FastAPI Integration

---

Developed as part of the SOAR Reinforcement Learning module.
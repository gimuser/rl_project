import csv
import os


class TrainingMetrics:
    """
    Store and save training metrics.
    """

    def __init__(self):
        self.episodes = []
        self.rewards = []
        self.losses = []
        self.epsilons = []

    def add(self, episode, reward, loss=None, epsilon=None):

        self.episodes.append(episode)
        self.rewards.append(reward)

        self.losses.append(
            0.0 if loss is None else float(loss)
        )

        self.epsilons.append(
            0.0 if epsilon is None else float(epsilon)
        )

    def average_reward(self):

        if not self.rewards:
            return 0.0

        return sum(self.rewards) / len(self.rewards)

    def total_reward(self):

        return sum(self.rewards)

    def print_summary(self):

        print("\n========== TRAINING SUMMARY ==========")
        print(f"Episodes       : {len(self.episodes)}")
        print(f"Total Reward   : {self.total_reward():.2f}")
        print(f"Average Reward : {self.average_reward():.2f}")

        if self.losses:
            print(f"Last Loss      : {self.losses[-1]:.6f}")

        if self.epsilons:
            print(f"Last Epsilon   : {self.epsilons[-1]:.4f}")

        print("======================================\n")

    def save_csv(self, filename="logs/training_metrics.csv"):

        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, "w", newline="") as file:

            writer = csv.writer(file)

            writer.writerow(
                [
                    "Episode",
                    "Reward",
                    "Loss",
                    "Epsilon",
                ]
            )

            for row in zip(
                self.episodes,
                self.rewards,
                self.losses,
                self.epsilons,
            ):
                writer.writerow(row)

        print(f"Metrics saved to {filename}")


if __name__ == "__main__":

    metrics = TrainingMetrics()

    metrics.add(1, 12.5, 0.08, 1.0)

    metrics.print_summary()

    metrics.save_csv()
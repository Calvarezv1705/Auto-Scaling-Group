import unittest

from controller.actuator import ASG_NAME, read_asg_state
from controller.decisor import decide


class FakeAutoScalingClient:
    """Simula la respuesta de AWS sin crear ni modificar recursos."""

    def describe_auto_scaling_groups(self, AutoScalingGroupNames):
        self.requested_names = AutoScalingGroupNames

        return {
            "AutoScalingGroups": [
                {
                    "MinSize": 1,
                    "MaxSize": 5,
                    "DesiredCapacity": 2,
                    "Instances": [
                        {
                            "LifecycleState": "InService",
                            "HealthStatus": "Healthy",
                        },
                        {
                            "LifecycleState": "InService",
                            "HealthStatus": "Unhealthy",
                        },
                        {
                            "LifecycleState": "Pending",
                            "HealthStatus": "Healthy",
                        },
                    ],
                }
            ]
        }


class ControllerTests(unittest.TestCase):

    def test_only_healthy_in_service_instances_are_counted(self):
        client = FakeAutoScalingClient()

        state = read_asg_state(client)

        self.assertEqual(client.requested_names, [ASG_NAME])
        self.assertEqual(state["desired"], 2)
        self.assertEqual(state["in_service"], 1)

    def test_high_demand_increases_capacity(self):
        decision, reason, target = decide(
            window=[89, 90, 74],
            healthy=1,
            desired=1,
        )

        self.assertEqual(decision, "INCREASE_CAPACITY")
        self.assertEqual(target, 2)

    def test_low_demand_reduces_capacity(self):
        decision, reason, target = decide(
            window=[15, 19, 22],
            healthy=2,
            desired=2,
        )

        self.assertEqual(decision, "REDUCE_CAPACITY")
        self.assertEqual(target, 1)

    def test_isolated_peak_maintains_capacity(self):
        decision, reason, target = decide(
            window=[20, 90, 20],
            healthy=2,
            desired=2,
        )

        self.assertEqual(decision, "MAINTAIN_CAPACITY")
        self.assertEqual(target, 2)


if __name__ == "__main__":
    unittest.main()
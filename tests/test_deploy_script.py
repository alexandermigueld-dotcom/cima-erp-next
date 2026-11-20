import unittest

from scripts.deploy_frappe_cloud import (
    PressClient,
    deploy,
    extract_cima_release,
    is_cima_up_to_date,
)


class FakePressClient(PressClient):
    def __init__(self, responses):
        super().__init__("k", "s")
        self.responses = responses
        self.calls = []

    def post(self, method, payload):
        self.calls.append((method, payload))
        return self.responses.get(method, (200, {"message": {}}))


class TestDeployFrappeCloud(unittest.TestCase):
    def test_extract_cima_release_picks_only_cima_ve(self):
        info = {
            "apps": [
                {
                    "name": "frappe",
                    "current_hash": "111",
                    "releases": [{"name": "r-frappe", "hash": "222"}],
                },
                {
                    "name": "cima_ve",
                    "current_hash": "a6b24fa",
                    "releases": [
                        {"name": "d8p6v2f80h", "hash": "f0a32efdde2753c3b9c5db825b3d990dd295545c"},
                    ],
                },
            ]
        }
        rel = extract_cima_release(info, target_sha="f0a32ef")
        self.assertEqual(
            rel,
            {
                "name": "cima_ve",
                "release": "d8p6v2f80h",
                "hash": "f0a32efdde2753c3b9c5db825b3d990dd295545c",
            },
        )
        self.assertFalse(is_cima_up_to_date(info, target_sha="f0a32ef"))

    def test_deploy_triggers_only_cima_ve_and_updates_site(self):
        client = FakePressClient(
            {
                "press.api.bench.fetch_latest_app_update": (200, {}),
                "press.api.bench.deploy_information": (
                    200,
                    {
                        "message": {
                            "deploy_in_progress": False,
                            "apps": [
                                {
                                    "name": "cima_ve",
                                    "current_hash": "a6b24fa",
                                    "update_available": True,
                                    "releases": [{"name": "d8p6v2f80h", "hash": "f0a32ef1234"}],
                                }
                            ],
                        }
                    },
                ),
                "press.api.bench.deploy": (200, {"message": "new_build_1"}),
                "press.api.site.check_for_updates": (200, {"message": {"update_available": True}}),
                "press.api.site.update": (200, {"message": "ok"}),
            }
        )
        rc = deploy(client, "bench-52215", "erpnext-yfl-bqf.v.frappe.cloud", target_sha="f0a32ef")
        self.assertEqual(rc, 0)
        deploy_calls = [p for m, p in client.calls if m == "press.api.bench.deploy"]
        self.assertEqual(len(deploy_calls), 1)
        self.assertEqual(
            deploy_calls[0]["apps"],
            [{"name": "cima_ve", "release": "d8p6v2f80h", "hash": "f0a32ef1234"}],
        )
        self.assertTrue(any(m == "press.api.site.update" for m, _ in client.calls))


if __name__ == "__main__":
    unittest.main()

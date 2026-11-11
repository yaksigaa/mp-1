import io
import unittest
from unittest.mock import patch
from app import app, init_db
from db import create_user, get_user_by_email

class TestFullFinLensSuite(unittest.TestCase):
    def setUp(self):
        init_db()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def test_auth_and_pages(self):
        # 1. Unauthenticated root redirect to login
        res = self.client.get("/")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers["Location"])

        # 2. Login page GET
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Welcome Back", res.data)

        # 3. Signup page GET
        res = self.client.get("/signup")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Create Account", res.data)

        # 4. Create user and login
        email = "full_suite_user@finlens.com"
        u = get_user_by_email(email)
        if not u:
            self.client.post("/signup", data={
                "name": "Suite User",
                "email": email,
                "password": "password123",
                "confirm_password": "password123"
            })
            u = get_user_by_email(email)

        login_res = self.client.post("/login", data={
            "email": email,
            "password": "password123"
        })
        self.assertEqual(login_res.status_code, 302)

        # 5. Dashboard page accessible when logged in
        dash_res = self.client.get("/")
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn(b"FinLens", dash_res.data)

        # 6. Current user endpoint
        me_res = self.client.get("/api/me")
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.get_json()["user"]["email"], email)

        # 7. Demo endpoint
        demo_res = self.client.get("/api/demo?z=3.0&drift=4.0")
        self.assertEqual(demo_res.status_code, 200)
        self.assertTrue(demo_res.get_json()["ok"])

        # 8. Reanalyse endpoint
        re_res = self.client.get("/api/reanalyse?z=2.5&drift=3.0")
        self.assertEqual(re_res.status_code, 200)
        self.assertTrue(re_res.get_json()["ok"])

        # 9. Stories endpoint
        st_res = self.client.get("/api/stories")
        self.assertEqual(st_res.status_code, 200)
        self.assertTrue(st_res.get_json()["ok"])

        # 10. History endpoint
        hist_res = self.client.get("/api/history")
        self.assertEqual(hist_res.status_code, 200)
        self.assertTrue(hist_res.get_json()["ok"])

        # 11. What-if endpoint
        wi_res = self.client.post("/api/whatif", json={
            "subscriptions": [{"merchant": "Netflix", "amount": 649, "active": True}],
            "cancel": ["Netflix"]
        })
        self.assertEqual(wi_res.status_code, 200)
        self.assertEqual(wi_res.get_json()["saved_monthly"], 649.0)

        # 12. Logout
        logout_res = self.client.get("/logout")
        self.assertEqual(logout_res.status_code, 302)

if __name__ == "__main__":
    unittest.main()


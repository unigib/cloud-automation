import os
import unittest
from unittest.mock import MagicMock, patch

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from lab_stack import StudentLabStack
from webapp import app as webapp
from webapp import init_db


class StackTests(unittest.TestCase):
    def test_stack_restricts_ingress_and_generates_secret(self):
        app = cdk.App(context={"allowed_ip": "8.8.8.8/32"})
        stack = StudentLabStack(
            app, "TestLab", env=cdk.Environment(account="123456789012", region="us-east-1")
        )
        template = Template.from_stack(stack)
        template.resource_count_is("AWS::EC2::Instance", 1)
        template.resource_count_is("AWS::SecretsManager::Secret", 1)
        template.has_resource_properties("AWS::SecretsManager::Secret", {
            "GenerateSecretString": {
                "SecretStringTemplate": '{"username":"labuser"}',
                "GenerateStringKey": "password",
                "ExcludePunctuation": True,
                "PasswordLength": 32,
            }
        })
        template.has_resource_properties("AWS::EC2::SecurityGroup", {
            "SecurityGroupIngress": [{
                "CidrIp": "8.8.8.8/32",
                "FromPort": 8080,
                "IpProtocol": "tcp",
                "ToPort": 8080,
                "Description": "Student web access",
            }]
        })
        template.has_resource_properties("AWS::EC2::Instance", {
            "UserData": Match.any_value(),
        })
        template.has_resource_properties("AWS::EC2::LaunchTemplate", {
            "LaunchTemplateData": {"MetadataOptions": {"HttpTokens": "required"}}
        })

    def test_rejects_missing_or_broad_access(self):
        for value in (None, "0.0.0.0/0", "10.0.0.1/32", "invalid"):
            with self.subTest(value=value):
                app = cdk.App(context={} if value is None else {"allowed_ip": value})
                with self.assertRaises(ValueError):
                    StudentLabStack(app, "InvalidLab")


class WebTests(unittest.TestCase):
    def setUp(self):
        self.client = webapp.app.test_client()
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.connect = patch.object(webapp, "connect", return_value=self.connection)
        self.connect.start()
        self.addCleanup(self.connect.stop)
        self.connection.__enter__.return_value = self.connection

    def test_message_is_parameterized_and_committed(self):
        response = self.client.post("/", data={"message": "  hello 'world'  "})
        self.assertEqual(response.status_code, 302)
        self.cursor.execute.assert_called_once_with(
            "INSERT INTO messages (message) VALUES (%s)", ("hello 'world'",)
        )
        self.connection.commit.assert_called_once()

    def test_invalid_messages_do_not_reach_database(self):
        for message in ("   ", "x" * 281):
            with self.subTest(message=message):
                self.assertEqual(self.client.post("/", data={"message": message}).status_code, 400)
        webapp.connect.assert_not_called()

    def test_messages_are_html_escaped(self):
        self.cursor.fetchall.return_value = [{"message": "<script>bad</script>", "created_at": "now"}]
        response = self.client.get("/")
        self.assertIn(b"&lt;script&gt;bad&lt;/script&gt;", response.data)
        self.assertNotIn(b"<script>bad</script>", response.data)


class ConnectionTests(unittest.TestCase):
    @patch.dict(os.environ, {"AWS_REGION": "us-east-1", "SECRET_ARN": "test-secret"})
    @patch("webapp.app.pymysql.connect")
    @patch("webapp.app.boto3.client")
    def test_connection_uses_the_secret_and_loopback(self, client, connect):
        client.return_value.get_secret_value.return_value = {
            "SecretString": '{"username":"labuser","password":"Secure123"}'
        }
        webapp.connect()
        self.assertEqual(connect.call_args.kwargs["host"], "127.0.0.1")
        self.assertEqual(connect.call_args.kwargs["user"], "labuser")
        self.assertEqual(connect.call_args.kwargs["password"], "Secure123")


class DatabaseInitTests(unittest.TestCase):
    @patch.dict(os.environ, {"AWS_REGION": "us-east-1", "SECRET_ARN": "test-secret"})
    @patch("webapp.init_db.subprocess.run")
    @patch("webapp.init_db.boto3.client")
    def test_initialization_passes_password_only_on_stdin(self, client, run):
        client.return_value.get_secret_value.return_value = {
            "SecretString": '{"username":"labuser","password":"Secure123"}'
        }
        init_db.main()
        args, kwargs = run.call_args
        self.assertNotIn("Secure123", " ".join(args[0]))
        self.assertIn("Secure123", kwargs["input"])
        self.assertTrue(kwargs["check"])

    @patch.dict(os.environ, {"AWS_REGION": "us-east-1", "SECRET_ARN": "test-secret"})
    @patch("webapp.init_db.subprocess.run")
    @patch("webapp.init_db.boto3.client")
    def test_rejects_unsafe_secret_before_running_sql(self, client, run):
        client.return_value.get_secret_value.return_value = {
            "SecretString": """{"username":"labuser","password":"bad'password"}"""
        }
        with self.assertRaises(ValueError):
            init_db.main()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

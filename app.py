#!/usr/bin/env python3
import os

import aws_cdk as cdk

from lab_stack import StudentLabStack


app = cdk.App()
StudentLabStack(
    app,
    "StudentWebLab",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION"),
    ),
)
app.synth()

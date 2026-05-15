import { app, HttpRequest, HttpResponseInit, InvocationContext, input } from "@azure/functions";

const signalRInput = input.generic({
  type: "signalRConnectionInfo",
  name: "connectionInfo",
  hubName: "o2monitor",
});

async function negotiate(
  request: HttpRequest,
  context: InvocationContext
): Promise<HttpResponseInit> {
  const connectionInfo = context.extraInputs.get(signalRInput);

  return {
    status: 200,
    jsonBody: connectionInfo,
  };
}

app.http("negotiate", {
  methods: ["POST"],
  authLevel: "anonymous",
  route: "negotiate",
  extraInputs: [signalRInput],
  handler: negotiate,
});

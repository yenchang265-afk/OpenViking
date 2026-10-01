## Step 1: Install the connector

1. Open Doubao Work, select **Skills · Connectors · Partners** in the sidebar, search for “Business Data Platform Context,” and select <strong>+</strong>.
![Add the Business Data Platform Context connector](https://docs.openviking.net/agents/image/doubao-work/01-add-connector.png)

2. Enter the Business Data Platform USER API key in the authorization dialog:

   ```text
   {{OPENVIKING_API_KEY}}
   ```

3. Select **Save and Connect**. Integration is complete when the “Connector installed” message appears and the <strong>+</strong> next to “Business Data Platform Context” changes to the added state.
![Save and connect Business Data Platform Context](https://docs.openviking.net/agents/image/doubao-work/02-save-and-connect.png)

## Step 2: Verify

1. Return to a Doubao conversation, select **Connectors** below the input box, and confirm that “Business Data Platform Context” is available.
![Verify the Business Data Platform Context connector](https://docs.openviking.net/agents/image/doubao-work/03-verify-connector.png)

2. Select **More Skills**, confirm that “Business Data Platform Context Database” is available, and ask Doubao to call Business Data Platform and return relevant content.
![Verify the Business Data Platform Context Database skill](https://docs.openviking.net/agents/image/doubao-work/04-verify-skill.png)

## Troubleshooting

| Issue | Resolution |
|---|---|
| “Business Data Platform Context” does not appear in search | Confirm that you are using Doubao Work, clear the search and try again; if it is still unavailable, ask your organization administrator whether the connector has been enabled |
| Connection fails | Check that the Business Data Platform USER API key is correct |

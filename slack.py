#References: https://tarunchawla.hashnode.dev/integrating-your-database-with-slack-using-mindsdb#heading-slack-integration

import os
import datetime as datetime
import ast
from typing import List
import pandas as pd
import evadb
from langchain import OpenAI
from langchain.agents import create_pandas_dataframe_agent
import pandas as pd

# Setting up the api key
import environ

env = environ.Env()
environ.Env.read_env()

API_KEY = env("apikey")

class SlackChannelsTable(APITable):
    def __init__(self, handler):
        """
        Checks the connection is active
        """
        super().__init__(handler)

    def select(self, query: ast.Select) -> Response:
        """
        Retrieves the data from the channel using SlackAPI
        Args:
            channel_name
        Returns:
            conversation_history
        """

        # Get the channels list and ids
        channels = self.client.conversations_list(types="public_channel,private_channel")['channels']
        channel_ids = {c['name']: c['id'] for c in channels}

        # Extract comparison conditions from the query
        conditions = extract_comparison_conditions(query.where)

        filters = []
        params = {}
        order_by_conditions = {}

        # Build the filters and parameters for the query
        for op, arg1, arg2 in conditions:
            if arg1 == 'channel':
                if arg2 in channel_ids:
                    params['channel'] = channel_ids[arg2]
                else:
                    raise ValueError(f"Channel '{arg2}' not found")

            elif arg1 == 'limit':
                if op == '=': 
                    params['limit'] = int(arg2)
                else:
                    raise NotImplementedError(f'Unknown op: {op}')

            else:
                filters.append([op, arg1, arg2])

        if query.limit:
            params['limit'] = int(query.limit.value)

        if query.order_by and len(query.order_by) > 0:
            order_by_conditions["columns"] = []
            order_by_conditions["ascending"] = []

            for an_order in query.order_by:
                if an_order.field.parts[1] == "messages":
                    order_by_conditions["columns"].append("messages")

                    if an_order.direction == "ASC":
                        order_by_conditions["ascending"].append(True)
                    else:
                        order_by_conditions["ascending"].append(False)
                else:
                    raise ValueError(
                        f"Order by unknown column {an_order.field.parts[1]}"
                    )

        # Retrieve the conversation history
        try:
            result = self.client.conversations_history(channel=params['channel'])
            conversation_history = result["messages"]
        except SlackApiError as e:
            log.logger.error("Error creating conversation: {}".format(e))

        # Get columns for the query and convert SlackResponse object to pandas DataFrame
        columns = []
        for target in query.targets:
            if isinstance(target, ast.Star):
                columns = []
                break
            elif isinstance(target, ast.Identifier):
                columns.append(target.parts[-1])
            else:
                raise NotImplementedError

        if len(columns) == 0:
            columns = self.get_columns()

        # columns to lower case
        columns = [name.lower() for name in columns]

        # convert SlackResponse object to pandas DataFrame
        result = pd.DataFrame(result['messages'], columns=columns)

        # add absent columns
        for col in set(columns) & set(result.columns) ^ set(columns):
            result[col] = None

        # filter by columns
        columns = [target.parts[-1].lower() for target in query.targets if isinstance(target, ast.Identifier)]
        result = result[columns]

        # Append the history to the response
        response_history = []
        for message in conversation_history:
            response_history.append(message['text'])
        result['messages'] = response_history

        # Sort the data based on order_by_conditions
        if len(order_by_conditions.get("columns", [])) > 0:
            result = result.sort_values(
                by=order_by_conditions["columns"],
                ascending=order_by_conditions["ascending"],
            )

        # Limit the result based on the query limit
        if query.limit:
            result = result.head(query.limit.value)

        # Alias the target column based on the query
        for target in query.targets:
            if target.alias:
                result.rename(columns={target.parts[-1]: str(target.alias)}, inplace=True)

        return result

    def get_columns(self):
        """
        Returns columns from the SlackAPI
        """

        return [
            'ts',
            'text',
            'user',
            'channel',
            'reactions',
            'attachments',
            'thread_ts',
            'reply_count',
            'reply_users_count',
            'latest_reply',
            'subtype',
            'hidden',
        ]

    def insert(self, query):
        """
        Inserts the message in the Slack Channel
        Args:
            channel_name
            message
        """

        # get column names and values from the query
        columns = [col.name for col in query.columns]
        for row in query.values:
            params = dict(zip(columns, row))

            # check if required parameters are provided
            if 'channel' not in params or 'message' not in params:
                raise Exception("To insert data into Slack, you need to provide the 'channel' and 'message' parameters.")

            # post message to Slack channel
            try:
                response = self.client.chat_postMessage(
                    channel=params['channel'],
                    text=params['message']
                )
            except SlackApiError as e:
                raise Exception(f"Error posting message to Slack channel '{params['channel']}': {e.response['error']}")

            inserted_id = response['ts']
            params['ts'] = inserted_id

    def update(self, query: ASTNode):
        """
        Updates the message in the Slack Channel
        Args:
            updated message
            channel_name
            ts  [TimeStamp -> Can be found by running select command, the entire result will be printed in the terminal]
        """

        # get column names and values from the query
        columns = [col.name for col in query.update_columns]
        for row in query.values:
            params = dict(zip(columns, row))

        # check if required parameters are provided
        if 'channel' not in params or 'ts' not in params or 'message' not in params:
            raise Exception("To update a message in Slack, you need to provide the 'channel', 'ts', and 'message' parameters.")

        # update message in Slack channel
        try:
            response = self.client.chat_update(
                channel=params['channel'],
                ts=params['ts'],
                text=params['message']
            )
        except SlackApiError as e:
            raise Exception(f"Error updating message in Slack channel '{params['channel']}' with timestamp '{params['ts']}': {e.response['error']}")

    def delete(self, query: ASTNode):
        """
        Deletes the message in the Slack Channel
        Args:
            channel_name
            ts  [TimeStamp -> Can be found by running select command, the entire result will be printed in the terminal]
        """

        # get column names and values from the query
        columns = [col.name for col in query.columns]
        for row in query.values:
            params = dict(zip(columns, row))

        # check if required parameters are provided
        if 'channel' not in params or 'ts' not in params:
            raise Exception("To delete a message from Slack, you need to provide the 'channel' and 'ts' parameters.")

        # delete message from Slack channel
        try:
            response = self.client.chat_delete(
                channel=params['channel'],
                ts=params['ts']
            )

        except SlackApiError as e:
            raise Exception(f"Error deleting message from Slack channel '{params['channel']}' with timestamp '{params['ts']}': {e.response['error']}")

class SlackHandler(APIHandler):
    """
    A class for handling connections and interactions with Slack API.
    Agrs:
        bot_token(str): The bot token for the Slack app.
    """

    def __init__(self, name=None, **kwargs):
        """
        Initializes the connection by checking all the params are provided by the user.
        """
        super().__init__(name)

        args = kwargs.get('connection_data', {})
        self.connection_args = {}
        handler_config = Config().get('slack_handler', {})
        for k in ['token']:
            if k in args:
                self.connection_args[k] = args[k]
            elif f'SLACK_{k.upper()}' in os.environ:
                self.connection_args[k] = os.environ[f'SLACK_{k.upper()}']
            elif k in handler_config:
                self.connection_args[k] = handler_config[k]
        self.api = None
        self.is_connected = False

        channels = SlackChannelsTable(self)
        self._register_table('channels', channels)

    def create_connection(self):
        """
        Creates a WebClient object to connect to the Slack API token stored in the connection_args attribute.
        """
        client = WebClient(token=self.connection_args['token'])
        return client

    def connect(self):
        """
        Authenticate with the Slack API using the token stored in the `token` attribute.
        """
        if self.is_connected is True:
            return self.api

        self.api = self.create_connection()
        return self.api

    def check_connection(self):
        """
        Checks the connection by calling auth_test()
        """
        response = StatusResponse(False)

        try:
            api = self.connect()

            # Call API method to check the connection
            api.auth_test()

            response.success = True
        except SlackApiError as e:
            response.error_message = f'Error connecting to Slack Api: {e.response["error"]}. Check token.'
            log.logger.error(response.error_message)

        if response.success is False and self.is_connected is True:
            self.is_connected = False

        return response

    def native_query(self, query_string: str = None):
        """
        Parses the query with FuncParser and calls call_slack_api and returns the result of the query as a Response object.
        """
        method_name, params = FuncParser().from_string(query_string)

        df = self.call_slack_api(method_name, params)

        return Response(
            RESPONSE_TYPE.TABLE,
            data_frame=df
        )

    def call_slack_api(self, method_name: str = None, params: dict = None):
        """
        Calls specific method specified.
        Args:
            method_name: to call specific method
            params: parameters to call the method
        Returns:
            List of dictionaries as a result of the method call
        """
        api = self.connect()
        method = getattr(api, method_name)

        try:
            result = method(**params)

        except SlackApiError as e:
            error = f"Error calling method '{method_name}' with params '{params}': {e.response['error']}"
            log.logger.error(error)
            raise e

        if 'channels' in result:
            result['channels'] = self.convert_channel_data(result['channels'])

        return [result]

    def convert_channel_data(self, channels: List[dict]):
        """
        Convert the list of channel dictionaries to a format that can be easily used in the data pipeline.
        Args:
            channels: A list of channel dictionaries.
        Returns:
            A list of channel dictionaries with modified keys and values.
        """

        new_channels = []
        for channel in channels:
            new_channel = {
                'id': channel['id'],
                'name': channel['name'],
                'created': datetime.fromtimestamp(float(channel['created']))
            }
            new_channels.append(new_channel)
        return new_channels
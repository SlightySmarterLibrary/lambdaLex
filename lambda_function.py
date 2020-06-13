"""
This sample demonstrates an implementation of the Lex Code Hook Interface
in order to serve a sample bot which manages orders for flowers.
Bot, Intent, and Slot models which are compatible with this sample can be found in the Lex Console
as part of the 'OrderFlowers' template.

For instructions on how to set up and test this bot, as well as additional samples,
visit the Lex Getting Started documentation http://docs.aws.amazon.com/lex/latest/dg/getting-started.html.
"""
import math
import dateutil.parser
import datetime
import time
import os
import logging
from datetime import date, timedelta, datetime
import json
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

import boto3
from boto3.dynamodb.conditions import Key, Attr

dynamodb = boto3.client('dynamodb', region_name='us-east-1')


""" --- Main handler --- """


def lambda_handler(event, context):
    """
    Route the incoming request based on intent.
    The JSON body of the request is provided in the event slot.
    """
    # By default, treat the user request as coming from the America/New_York time zone.
    os.environ['TZ'] = 'America/New_York'
    time.tzset()
    logger.debug('event.bot.name={}'.format(event['bot']['name']))

    return dispatch(event)


""" --- Helpers to build responses which match the structure of the necessary dialog actions --- """


def get_slots(intent_request):
    return intent_request['currentIntent']['slots']


def elicit_slot(session_attributes, intent_name, slots, slot_to_elicit, message):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'ElicitSlot',
            'intentName': intent_name,
            'slots': slots,
            'slotToElicit': slot_to_elicit,
            'message': message
        }
    }


def close(session_attributes, fulfillment_state, message):
    response = {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Close',
            'fulfillmentState': fulfillment_state,
            'message': message
        }
    }

    return response


def delegate(session_attributes, slots):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Delegate',
            'slots': slots
        }
    }


""" --- Helper Functions --- """


def parse_int(n):
    try:
        return int(n)
    except ValueError:
        return float('nan')


def build_validation_result(is_valid, violated_slot, message_content):
    if message_content is None:
        return {
            "isValid": is_valid,
            "violatedSlot": violated_slot,
        }

    return {
        'isValid': is_valid,
        'violatedSlot': violated_slot,
        'message': {'contentType': 'PlainText', 'content': message_content}
    }


def isvalid_date(date):
    try:
        dateutil.parser.parse(date)
        return True
    except ValueError:
        return False


def validate_order_flowers(BookName, AuthorName, email):

    
    if BookName is not None and AuthorName is not None and email is not None:
        # if book does not exist
        dyndb = boto3.resource('dynamodb')
        table = dyndb.Table('books')
        # response = table.scan(
        # ProjectionExpression= "#name, author, id, reserved",
        # FilterExpression= "(#name = :bookname) AND (author = :authorName)",
        # ExpressionAttributeNames={'#name': 'name'},
        # ExpressionAttributeValues= {
        #     ":bookname": {"S": BookName},
        #     ":authorName": {"S": AuthorName}
        #     }
        # )
        filter_expression = '(#name = :n) AND (author = :a)'
        attr_values = {':n': BookName, ':a':AuthorName}
        response = table.scan(
            FilterExpression=filter_expression,
            ExpressionAttributeNames={'#name': 'name'},
            ExpressionAttributeValues=attr_values
        )

        print(response)


        if not response['Items']:
            return build_validation_result(False, 'BookName', "Sorry, we don't have that book. Please type reserve to look for another book.")
        else:
            # only get the first
            item = response['Items'][0]
            reserved = item['reserved']
            if reserved == "true":
                return build_validation_result(False, 'BookName', "Sorry, that book is already reserved. Please type reserve to look for another book.")
            else:
                # update reservation 
                name = item['name']
                bookid =  item['id']
                author = item['author']
                dynamodbresource = boto3.resource('dynamodb', region_name='us-east-1')
                books = dynamodbresource.Table('books')
                reservation = dynamodbresource.Table('reservation')
                print("Update " + name)
                response = books.update_item(
                    Key={
                        'id': bookid
                    },
                    UpdateExpression='SET reserved = :r, reserved_by = :p',
                    ExpressionAttributeValues={
                        ':r': "true",
                        ':p': email
                    }
                )
                print(response)
                date = datetime.today()
                expiry = datetime.today() + timedelta(days=7)
                expiry = expiry.strftime('%m-%d-%Y')
                fakeid = date.strftime('%m-%d-%Y-%H:%M:%S') + " " + email
                dynamodb.put_item(
                    TableName='reservation',
                    Item={
                    "book_id": {"S": f"{bookid}"},
                    "id": {"S": f"{fakeid}"},
                    "created_at": {"S": f"{date}"},
                    "expiration": {"S": f"{expiry}"},
                    "book_name": {"S": f"{name}"},
                    "user_id": {"S": f"{email}"}
                    }
                )
                return build_validation_result(False, 'BookName', "Thanks for booking, your reservation will expire on " + expiry + ".")
           


    #        
    return build_validation_result(True, None, None)


""" --- Functions that control the bot's behavior --- """


def order_flowers(intent_request):
    """
    Performs dialog management and fulfillment for ordering flowers.
    Beyond fulfillment, the implementation of this intent demonstrates the use of the elicitSlot dialog action
    in slot validation and re-prompting.
    """

    bookName = get_slots(intent_request)["BookName"]
    authorName = get_slots(intent_request)["AuthorName"]
    email = get_slots(intent_request)["email"]
    source = intent_request['invocationSource']

    if source == 'DialogCodeHook':
        # Perform basic validation on the supplied input slots.
        # Use the elicitSlot dialog action to re-prompt for the first violation detected.
        slots = get_slots(intent_request)

        validation_result = validate_order_flowers(bookName, authorName, email)
        if not validation_result['isValid']:
            slots[validation_result['violatedSlot']] = None
            return elicit_slot(intent_request['sessionAttributes'],
                               intent_request['currentIntent']['name'],
                               slots,
                               validation_result['violatedSlot'],
                               validation_result['message'])

        # Pass the price of the flowers back through session attributes to be used in various prompts defined
        # on the bot model.
        output_session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}
        # if flower_type is not None:
        #     output_session_attributes['Price'] = len(flower_type) * 5  # Elegant pricing model

        return delegate(output_session_attributes, get_slots(intent_request))

    # Order the flowers, and rely on the goodbye message of the bot to define the message to the end user.
    # In a real bot, this would likely involve a call to a backend service.
    return close(intent_request['sessionAttributes'],
                 'Fulfilled',
                 {'contentType': 'PlainText',
                  'content': 'Thanks, your order for {} has been placed'.format(bookName)})


""" --- Intents --- """


def dispatch(intent_request):
    """
    Called when the user specifies an intent for this bot.
    """

    logger.debug('dispatch userId={}, intentName={}'.format(intent_request['userId'], intent_request['currentIntent']['name']))

    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'ReserveBook':
        return order_flowers(intent_request)

    raise Exception('Intent with name ' + intent_name + ' not supported')


# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt import mqtt
import sys
import threading
import time
from uuid import uuid4
import json
import datetime
import socket

# This sample uses the Message Broker for AWS IoT to send and receive messages
# through an MQTT connection. On startup, the device connects to the server,
# subscribes to a topic, and begins publishing messages to that topic.
# The device should receive those same messages back from the message broker,
# since it is subscribed to that same topic.

# Parse arguments
import command_line_utils;
cmdUtils = command_line_utils.CommandLineUtils("PubSub - Send and recieve messages through an MQTT connection.")
cmdUtils.add_common_mqtt_commands()
cmdUtils.add_common_topic_message_commands()
cmdUtils.add_common_proxy_commands()
cmdUtils.add_common_logging_commands()
cmdUtils.register_command("key", "<path>", "Path to your key in PEM format.", True, str)
cmdUtils.register_command("cert", "<path>", "Path to your client certificate in PEM format.", True, str)
cmdUtils.register_command("port", "<int>", "Connection port. AWS IoT supports 443 and 8883 (optional, default=auto).", type=int)
cmdUtils.register_command("client_id", "<str>", "Client ID to use for MQTT connection (optional, default='test-*').", default="test-" + str(uuid4()))
cmdUtils.register_command("count", "<int>", "The number of messages to send (optional, default='10').", default=10, type=int)
cmdUtils.register_command("is_ci", "<str>", "If present the sample will run in CI mode (optional, default='None')")
cmdUtils.register_command("id", "<str>", "Name of the operator (optional, default='None')")
cmdUtils.register_command("temp", "<str>", "Temperature of the Instrument, default=25)")
# Needs to be called so the command utils parse the commands
cmdUtils.get_args()

received_count = 0
received_all_event = threading.Event()
is_ci = cmdUtils.get_command("is_ci", None) != None

# Callback when connection is accidentally lost.
def on_connection_interrupted(connection, error, **kwargs):
    print("Connection interrupted. error: {}".format(error))


# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print("Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))

    if return_code == mqtt.ConnectReturnCode.ACCEPTED and not session_present:
        print("Session did not persist. Resubscribing to existing topics...")
        resubscribe_future, _ = connection.resubscribe_existing_topics()

        # Cannot synchronously wait for resubscribe result because we're on the connection's event-loop thread,
        # evaluate result with a callback instead.
        resubscribe_future.add_done_callback(on_resubscribe_complete)


def on_resubscribe_complete(resubscribe_future):
        resubscribe_results = resubscribe_future.result()
        print("Resubscribe results: {}".format(resubscribe_results))

        for topic, qos in resubscribe_results['topics']:
            if qos is None:
                sys.exit("Server rejected resubscribe to topic: {}".format(topic))


# Callback when the subscribed topic receives a message
def on_message_received(topic, payload, dup, qos, retain, **kwargs):
    print("Received message from topic '{}': {}".format(topic, payload))
    global received_count
    received_count += 1
    if received_count == cmdUtils.get_command("count"):
        received_all_event.set()

if __name__ == '__main__':
    useSubscribe = False
    useDemo = False
    sendstatus = True
    sendToS3 = False
    SendEndOfRun = False
    clientID = "basicPubSub"
    mqtt_connection = cmdUtils.build_mqtt_connection(on_connection_interrupted, on_connection_resumed)

    if is_ci == False:
        print("Connecting to {} with client ID '{}'...".format(
            cmdUtils.get_command(cmdUtils.m_cmd_endpoint), cmdUtils.get_command("client_id")))
    else:
        print("Connecting to endpoint with client ID")
    connect_future = mqtt_connection.connect()

    # Future.result() waits until a result is available
    connect_future.result()
    print("Connected!")

    message_count = cmdUtils.get_command("count")
    operator = cmdUtils.get_command("id")
    instrumentTemperature = cmdUtils.get_command("temp")
    message_topic = cmdUtils.get_command(cmdUtils.m_cmd_topic)
    print(message_topic)

    # send to device
    message_publish = message_topic
    #message_publish_s3 = "iotdevice/kirtLaptop/data"
    #message_publish_event = "device/kirtLaptop/event"
    
    print(f"subscribe {message_topic} and publish {message_publish}")
    message_string = "Instrument message" #cmdUtils.get_command(cmdUtils.m_cmd_message)

    # Subscribe
    if useSubscribe:
        print("Subscribing to topic '{}'...".format(message_topic))
        subscribe_future, packet_id = mqtt_connection.subscribe(
            topic=message_topic,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_message_received)

        subscribe_result = subscribe_future.result()
        print("Subscribed with {}".format(str(subscribe_result['qos'])))

    # Publish message to server desired number of times.
    # This step is skipped if message is blank.
    # This step loops forever if count was set to 0.
    print(f"sending message {message_string} for operator {operator}")
    if message_string:
        if message_count == 0:
            print ("Sending messages until program killed")
        else:
            print (f"Sending {message_count} message(s) to {message_publish}")

        publish_count = 1
        while (publish_count <= message_count) or (message_count == 0):
            temp = instrumentTemperature
            data = [{
                "datetime": str(datetime.datetime.now()),
                "message": "We are testing BB4 communications. Pls forward this communication to khaden@encodia.com",
                "subject": "Testing Instrument Events",
                "operator": "VN",
                "messagetype": "SMS",
                "source": socket.gethostname(),
            }]

            message_string = json.dumps(data)
            message = message_string.strip('[').strip(']') 
            print("Publishing message to topic '{}': {}".format(message_publish, message))
            message_json = message
            if sendstatus:
                mqtt_connection.publish(
                    topic=message_publish,
                    payload=message_json,
                    qos=mqtt.QoS.AT_LEAST_ONCE)
                print(f"send complete for {message_publish}")
            
            #send to S3 also
            if sendToS3:
                mqtt_connection.publish(
                    topic=message_publish_s3,
                    payload=message_json,
                    qos=mqtt.QoS.AT_LEAST_ONCE)
                print(f"send complete for {message_publish_s3}")

            
            #send to IotEvent also
            if SendEndOfRun:
                mqtt_connection.publish(
                    topic=message_publish_event,
                    payload=message_json,
                    qos=mqtt.QoS.AT_LEAST_ONCE)
                print(f"send complete for {message_publish_event}")

            time.sleep(1)

            publish_count += 1

    # Wait for all messages to be received.
    # This waits forever if count was set to 0.
    if useSubscribe:
        if message_count != 0 and not received_all_event.is_set():
            print("Waiting for all messages to be received...")

        received_all_event.wait()
        print("{} message(s) received.".format(received_count))

    # Disconnect
    print("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    print("Disconnected!")

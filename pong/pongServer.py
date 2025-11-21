# =================================================================================================
# Contributing Authors:	    <Anyone who touched the code>
# Email Addresses:          <Your uky.edu email addresses>
# Date:                     <The date the file was last edited>
# Purpose:                  <How this file contributes to the project>
# Misc:                     <Not Required.  Anything else you might want to include>
# =================================================================================================

import socket
import threading
import json
import time
from threading import Lock

#Initialization variables used to create game state and initialize the clients
SCREEN_WIDTH : int = 480
SCREEN_HEIGHT : int = 640
PADDLE_START_Y : int = (SCREEN_HEIGHT/2)

#Create dictionary to store current game state
game_data = {
    "left_paddle_y": PADDLE_START_Y,
    "right_paddle_y": PADDLE_START_Y,
    "ball_x": SCREEN_WIDTH/2,
    "ball_y": SCREEN_HEIGHT/2,
    "left_score": 0,
    "right_score": 0,
    "left_sync": 0,
    "right_sync": 0
}

#Store ball pos and prospective scores to find most updated 
left_ball_pos : list[int] = [game_data["ball_x"], game_data["ball_y"]]
right_ball_pos : list[int] = [game_data["ball_x"], game_data["ball_y"]]
scores : list[list[int]] = [[0,0], [0,0]]

#Create a mutex
mutex = threading.Lock()

def acceptor() -> None:

# Author: Parker Jenkins
# Purpose: Accepts sockets and adds them to a list to track who is connected
# Pre: This method expects there to be clients not assigned a role
# Post: This method assigns users a role and allows them to start sending and recieving data

    while True:
        try:
            client_sock, client_addr = sock.accept()
            
            with mutex:
                client_sockets.append(client_sock)
                threading.Thread( target = handle_clients, args = (client_sock,)).start()
        except socket.timeout:
            pass

#TO FINISH ADD SPECTATOR HANDLING
def handle_clients( conn : socket.socket) -> None:
    # Author: Parker Jenkins
    # Purpose: Accepts sockets and assigns them roles
    # Pre: This method expects there to be clients attempting to connect
    # Post: This method changes one of the global variables to store sockets with one pointing to the proper client

    global left_sock, right_sock, spec_sock #define as global so the value is non local
    paddle_side : str
    with mutex: #Place mutex lock to ensure only one in each paddle, rest are spectators
        
        if left_sock is None:
            left_sock = conn
            paddle_side = "left"

        elif right_sock is None:
            right_sock = conn
            paddle_side = "right"

        else:
            spec_sock.append(conn)
            paddle_side = "spectator"
        
    init_game_state : dict = {
        "screen_width" : SCREEN_WIDTH,
        "screen_height" : SCREEN_HEIGHT,
        "paddle" : paddle_side
    }
    try:
        conn.sendall(json.dumps(init_game_state).encode("utf-8"))
        
        while True:    

            if conn not in spec_sock:
                msg : str = conn.recv(1024) #Recieve Data from client

                if not msg:
                    break

                data = json.loads(msg.decode("utf-8"))

                with mutex:

                    if conn == left_sock:
                        game_data["left_paddle_y"] =  data["paddle_y"]
                        game_data["left_sync"] = data["sync"]
                        left_ball_pos[0] = data["ball_x"]
                        left_ball_pos[1] = data["ball_y"]
                        scores[0][0] = data["lscore"]
                        scores[0][1] = data["rscore"]
                    elif conn == right_sock:
                        game_data["right_paddle_y"] =  data["paddle_y"]
                        game_data["right_sync"] = data["sync"]
                        right_ball_pos[0] = data["ball_x"]
                        right_ball_pos[1] = data["ball_y"]
                        scores[1][0] = data["lscore"]
                        scores[1][1] = data["rscore"]

            elif conn in spec_sock:
                msg = conn.recv(1024)

                if not msg:
                    break
        #Continue from here to handle clients (reecieve data and send data w funcs and logic to sync)

    finally:
        with mutex:
           if conn == left_sock:
               left_sock = None
           elif conn == right_sock:
               right_sock = None
           elif conn in spec_sock:
               spec_sock.remove(conn)
           
           if conn in client_sockets:
               client_sockets.remove(conn)
       
        conn.close()

def update_game_vals() -> None:
    # Author: Parker Jenkins
    # Purpose: Decide which client is the most updated
    # Pre: This method expects there to be clients connected and transmitting
    # Post: This method changes the game state and transmits it to the clients

    while True:
        time.sleep(1/60) #Update 60 times per second, can change update rate in this line

        with mutex:

            #If the left sync is higher, it is ahead, so use its values
            if game_data["left_sync"] > game_data["right_sync"]:
                game_data["ball_x"] = left_ball_pos[0]
                game_data["ball_y"] = left_ball_pos[1]
                game_data["left_score"] = scores[0][0]
                game_data["right_score"] = scores[0][1]
            #If the right side is as updated or ahead, use the stats for the right player
            else: 
                game_data["ball_x"] = right_ball_pos[0]
                game_data["ball_y"] = right_ball_pos[1]
                game_data["left_score"] = scores[1][0]
                game_data["right_score"] = scores[1][1]

        #Send the game state to the players
        if left_sock:
            left_sock.sendall(json.dumps(game_data).encode("utf-8"))
        if right_sock:
            right_sock.sendall(json.dumps(game_data).encode("utf-8"))
        if spec_sock:
            for c in spec_sock:
                c.sendall(json.dumps(game_data).encode("utf-8"))


#These will store the sockets for each role
left_sock : socket.socket = None
right_sock : socket.socket = None
spec_sock : list[socket.socket] = list()

#This stores the needed IP and Port to establish a server
LAN_IP : str = "0.0.0.0"
PORT : int = 50000

#Create the socket and bind it
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind((LAN_IP, PORT))

#This list tracks who is connected
client_sockets : list[socket.socket] = list()

#Listen to the socket for people attempting to connect and start a thread to accept them
sock.listen()
threading.Thread(target = acceptor).start()
threading.Thread(target=update_game_vals, daemon=True).start()

try:
    while True:
       time.sleep(1)
except KeyboardInterrupt:
    sock.close()
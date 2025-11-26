# =================================================================================================
# Contributing Authors:	Parker Jenkins 
# Email Addresses: prje222@uky.edu 
# Date: 11/25/2025
# Purpose: Establishes a server and handles all connections from any client. 
# Supports 2 players and many spectators for a game of pong. Sends inital game state to 
# all clients, receives data from clients, parses data to update game state and send new
# game state to clients for updating.
# =================================================================================================

import socket
import threading
import json
import time

#Initialization of variables used to create game state and initialize the clients
SCREEN_WIDTH : int = 480
SCREEN_HEIGHT : int = 640
PADDLE_START_Y : int = (SCREEN_HEIGHT/2)

left_sock : socket.socket
right_sock : socket.socket
spec_sock : list[socket.socket]
left_sync : int
right_sync : int

#Create dictionary to store current game state
game_data = {
    "left_paddle_y": PADDLE_START_Y,
    "right_paddle_y": PADDLE_START_Y,
    "ball_x": SCREEN_WIDTH/2,
    "ball_y": SCREEN_HEIGHT/2,
    "left_score": 0,
    "right_score": 0,
    "max_sync": 0,
    "num_players" : 0
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
# Pre: This method expects there to be clients attempting to connect
# Post: This method assigns users a role and allows them to start sending and recieving data as necessary

    while True:
        try:
            client_sock, client_addr = sock.accept() #Accept all clients
            
            with mutex:
                client_sockets.append(client_sock) #Append to the client sock list
                threading.Thread( target = handle_clients, args = (client_sock,)).start() #Start a thread to handle the client
        except socket.timeout:
            pass

def handle_clients( conn : socket.socket) -> None:
    # Author: Parker Jenkins
    # Purpose: Accepts sockets and assigns them roles
    # Pre: This method expects there to be clients attempting to connect
    # Post: This method changes one of the global variables to store sockets with one pointing to the proper client

    global left_sock, right_sock, spec_sock #Define as global so the value is non local for player possitions and their sockets
    paddle_side : str #Holds player position to send to client
    global left_sync, right_sync #Define as global for access of the players' sync across threads

    with mutex: #Place mutex lock to ensure only one in each paddle, rest are spectators
        
        #Add first connection to the left player
        if left_sock is None:
            left_sock = conn
            paddle_side = "left"
            print(f"LEFT SIDE IS: {left_sock}")
            game_data["num_players"] += 1

        #Add second connection to right side
        elif right_sock is None:
            right_sock = conn
            paddle_side = "right"
            print(f"RIGHT SIDE IS: {right_sock}")
            game_data["num_players"] += 1

        #Add everyone else to the spectators
        else:
            spec_sock.append(conn)
            paddle_side = "spectator"
        
    #Create initial game state dictionary to send at the start of the game to each player
    init_game_state : dict = {
        "screen_width" : SCREEN_WIDTH,
        "screen_height" : SCREEN_HEIGHT,
        "paddle" : paddle_side
    }

    #Per-connection JSON stream buffer / decoder
    decoder = json.JSONDecoder()
    buffer = ""

    try:
        #Send the initial game state
        conn.sendall(json.dumps(init_game_state).encode("utf-8"))

        #Send initial data and immediatly send an "update" to ensure there were no issues establishing the start screen
        with mutex:
            initial_update = json.dumps(game_data).encode("utf-8")
        conn.sendall(initial_update)

        #Stay in loop for sending and recieving data
        while True:    

            msg : str = conn.recv(1024) #Recieve Data from client

            #If the message is empty break
            if not msg:
                break
                
            # Spectators don't send structured game updates; just keep them alive
            if conn in spec_sock:
                continue

            buffer += msg.decode("utf-8") #Add the message to the buffer

            # Pull as many complete JSON objects as we can from buffer
            while buffer:
                try:
                    obj, idx = decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    # Not enough data yet for a full JSON object
                    break

                buffer = buffer[idx:].lstrip()

                with mutex: #Lock threads to ensure no race conditions while updating the game state

                    #Update the game data with the data recieved from the left side
                    if conn == left_sock:
                        game_data["left_paddle_y"] =  obj["paddle_y"]
                        left_sync = obj["sync"]
                        left_ball_pos[0] = obj["ball_x"]
                        left_ball_pos[1] = obj["ball_y"]
                        scores[0][0] = obj["lscore"]
                        scores[0][1] = obj["rscore"]
                    
                    #Update the game data with the data recieved from the right side
                    elif conn == right_sock:
                        game_data["right_paddle_y"] =  obj["paddle_y"]
                        right_sync = obj["sync"]
                        right_ball_pos[0] = obj["ball_x"]
                        right_ball_pos[1] = obj["ball_y"]
                        scores[1][0] = obj["lscore"]
                        scores[1][1] = obj["rscore"]
    
    except (ConnectionResetError, BrokenPipeError, OSError): #Handle expected errors for disconnecting
        pass

    #After the try block, clear variables and close connection
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
       
       #Disconnect the client
        conn.close()

def update_game_vals() -> None:
    # Author: Parker Jenkins
    # Purpose: Decide which client is the most updated
    # Pre: This method expects there to be clients connected and transmitting
    # Post: This method changes the game state and transmits it to the clients

    while True:
        time.sleep(1/60) #Update 60 times per second, can change update rate in this line
        with mutex:
            
            #Decide the dominant player and ensure the max sync matches the clients data
            if left_sync is not None and right_sync is not None:
                use_left = left_sync >= right_sync
                game_data["max_sync"] = max(left_sync, right_sync)
            elif left_sync is not None:
                use_left = True
                game_data["max_sync"] = left_sync
            elif right_sync is not None:
                use_left = False
                game_data["max_sync"] = right_sync
            else:
                continue

            #If the left sync is higher, it is ahead, so use its values for score and ball position
            if use_left:
                game_data["ball_x"] = left_ball_pos[0]
                game_data["ball_y"] = left_ball_pos[1]
                game_data["left_score"] = scores[0][0]
                game_data["right_score"] = scores[0][1]
            #If the right sync is higher, it is ahead, so use its values for score and ball position
            else: 
                game_data["ball_x"] = right_ball_pos[0]
                game_data["ball_y"] = right_ball_pos[1]
                game_data["left_score"] = scores[1][0]
                game_data["right_score"] = scores[1][1]

            #Paddles stay in game_data["left_paddle_y"] / ["right_paddle_y"]
            #Create json of updated game state ready to send
            payload = json.dumps(game_data).encode("utf-8")

        #Send the game state to the players and prevenet errors for stopping exectution
        if left_sock:
            try:
                left_sock.sendall(payload)
            except OSError:
                pass
        if right_sock:
            try:
                right_sock.sendall(payload)
            except OSError:
                pass
        for c in list(spec_sock):
            try:
                c.sendall(payload)
            except OSError:
                pass


#These will store the sockets for each role
left_sock : socket.socket = None
right_sock : socket.socket = None
left_sync : int = None
right_sync : int = None
spec_sock : list[socket.socket] = list()

#This stores the needed IP and Port to establish a server
LAN_IP : str = "0.0.0.0"
PORT : int = 50505

#Get the Ip to enter on other devices
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) #Create a UDP Socket
s.connect(("8.8.8.8", 80)) #Connect to Googles public DNS server
LOCAL_IP : str = s.getsockname()[0] #Pull the ip from the tuple returned by getsockname()
s.close() #Close the connection

#Display the needed information to connect
print(f"Listening on IP: {LOCAL_IP} and Port: {PORT}")

#Create the socket and bind it
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind((LAN_IP, PORT))

#This list tracks who is connected
client_sockets : list[socket.socket] = list()

#Listen to the socket for people attempting to connect and start a thread to accept them
sock.listen()
threading.Thread(target = acceptor).start()

#Start a thread to update values of the game state based on dominant player
threading.Thread(target=update_game_vals, daemon=True).start()

try:
    #Keep the main thread running until a keyboard interrupt
    while True:
       time.sleep(1)
except KeyboardInterrupt:
    #Ensure all client connections are closed in case of previous error
    if len(client_sockets) != 0:
        for c in client_sockets:
            c.close() 
    sock.close()

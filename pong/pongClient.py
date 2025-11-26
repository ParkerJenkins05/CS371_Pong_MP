# =================================================================================================
# Contributing Authors:	    Nebojsa Simic, Donovan Jenkins
# Email Addresses:          nsi255@uky.edu, donovan.jenkins@uky.edu
# Date:                     11/25/2025
# Purpose:                  This file implements the client side of the multiplayer Pong system. It 
# connects to the server through a TCP socket, receives the initial game configuration, and launches 
# the local Pygame instance. The client gathers input from the user, sends paddle and gameplay updates 
# back to the server, and applies the server’s authoritative state for ball position, opponent paddle 
# movement, scoring, and synchronization. It also supports multiple spectators by rendering the game 
# entirely from server updates. A background networking thread ensures the game loop remains smooth 
# while maintaining real-time communication with the server.
# Misc:                     <Not Required.  Anything else you might want to include>
# =================================================================================================

import pygame
import tkinter as tk
import sys
import socket
from PIL import Image, ImageTk
from pathlib import Path
import json # added
import threading # added

from assets.code.helperCode import *

# Author: Nebojsa Simic
# Purpose: Maintain a shared copy of the server's authoritative game state on the client.
# Pre: Client must already be connected to the server and be receiving JSON updates.
# Post: The dictionary server state always holds the most recent paddle positions, ball
#       position, scores, and sync metadata received from the server, protected by state_lock.

# simple shared state from server
server_state = {
    "left_paddle_y": None,
    "right_paddle_y": None,
    "ball_x": None,
    "ball_y": None,
    "left_score": None,
    "right_score": None,
    "max_sync" : None,
    "num_players" : None
}
state_lock = threading.Lock()

# Author: Nebojsa Simic
# Purpose: Run in a background thread to continuously receive and decode JSON game updates
#          from the server without blocking the main Pygame loop.
# Pre: The client socket must be connected to the Pong server and sending complete JSON
#       objects (no delimiters, possibly multiple objects in one TCP packet).
# Post: Incoming JSON messages are parsed out of the byte stream and used to update
#       server_state under state_lock so the main game loop can safely read the latest data.

def recv_loop(client:socket.socket) -> None:
    # background loop that receives game state from the server
    buffer = ""
    decoder = json.JSONDecoder()
    while True:
        try:
            data = client.recv(1024)
            if not data:
                break
            buffer += data.decode("utf-8")
            # try to pull as many full JSON objects available in buffer
            while buffer:
                try:
                    obj, idx = decoder.raw_decode(buffer)
                except json.JSONDecodeError:        # not enough data for full JSON object
                    break
                buffer = buffer[idx:].lstrip()

                with state_lock:
                    for k in server_state:
                        if k in obj:
                            server_state[k] = obj[k]
        except OSError:
            break
        except:
            break
# This is the main game loop.  For the most part, you will not need to modify this.  The sections
# where you should add to the code are marked.  Feel free to change any part of this project
# to suit your needs.
def playGame(screenWidth:int, screenHeight:int, playerPaddle:str, client:socket.socket) -> None:
    
    # Pygame inits
    pygame.mixer.pre_init(44100, -16, 2, 2048)
    pygame.init()

    # Constants
    WHITE = (255,255,255)
    clock = pygame.time.Clock()
    scoreFont = pygame.font.Font("./assets/fonts/pong-score.ttf", 32)
    winFont = pygame.font.Font("./assets/fonts/visitor.ttf", 48)
    pointSound = pygame.mixer.Sound("./assets/sounds/point.wav")
    bounceSound = pygame.mixer.Sound("./assets/sounds/bounce.wav")

    # Display objects
    screen = pygame.display.set_mode((screenWidth, screenHeight))
    winMessage = pygame.Rect(0,0,0,0)
    topWall = pygame.Rect(-10,0,screenWidth+20, 10)
    bottomWall = pygame.Rect(-10, screenHeight-10, screenWidth+20, 10)
    centerLine = []
    for i in range(0, screenHeight, 10):
        centerLine.append(pygame.Rect((screenWidth/2)-5,i,5,5))

    # Paddle properties and init
    paddleHeight = 50
    paddleWidth = 10
    paddleStartPosY = (screenHeight/2)-(paddleHeight/2)
    leftPaddle = Paddle(pygame.Rect(10,paddleStartPosY, paddleWidth, paddleHeight))
    rightPaddle = Paddle(pygame.Rect(screenWidth-20, paddleStartPosY, paddleWidth, paddleHeight))

    ball = Ball(pygame.Rect(screenWidth/2, screenHeight/2, 5, 5), -5, 0)

    if playerPaddle == "left":
        opponentPaddleObj = rightPaddle
        playerPaddleObj = leftPaddle
    else:
        opponentPaddleObj = leftPaddle
        playerPaddleObj = rightPaddle

    lScore = 0
    rScore = 0

    sync = 0

    netBuffer = ""  # small buffer used to accumulate json from server
    isSpectator = (playerPaddle == "spectator") # boolean to check if player is a spectator

    while True:
        # Wiping the screen
        screen.fill((0,0,0))

        # Getting keypress events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_DOWN:
                    playerPaddleObj.moving = "down"

                elif event.key == pygame.K_UP:
                    playerPaddleObj.moving = "up"

            elif event.type == pygame.KEYUP:
                playerPaddleObj.moving = ""

        # =========================================================================================
        # Your code here to send an update to the server on your paddle's information,
        # where the ball is and the current score.
        # Feel free to change when the score is updated to suit your needs/requirements
        # Author: Donovan Jenkins
        # Purpose: Send the local player's current paddle position, ball position, score,
        #           and sync counter to the server so it can decide which client is ahead
        #           in time and broadcast an authoritative game state.
        # Pre: The client socket must be connected and the player must not be a spectator.
        # Post: The server receives one JSON object per frame from this client that can be
        #       merged with the other player's data to update the global game_data.

        if client is not None and not isSpectator:
            update_msg = {
                "paddle_y": int(playerPaddleObj.rect.y),
                "sync": int(sync),
                "ball_x": int(ball.rect.x),
                "ball_y": int(ball.rect.y),
                "lscore": int(lScore),
                "rscore": int(rScore)
            }
            try:
                client.sendall(json.dumps(update_msg).encode("utf-8"))
            except:
                pass

        # update the player paddle and opponent paddle location on the screen
        for paddle in [playerPaddleObj, opponentPaddleObj]:
            if paddle.moving == "down":
                if paddle.rect.bottomleft[1] < screenHeight-10:
                    paddle.rect.y += paddle.speed
            elif paddle.moving == "up":
                if paddle.rect.topleft[1] > 10:
                    paddle.rect.y -= paddle.speed

        # if game is over, display the win message
        if lScore > 4 or rScore > 4:
            winText = "Player 1 Wins! " if lScore > 4 else "Player 2 Wins! "
            textSurface = winFont.render(winText, False, WHITE, (0,0,0))
            textRect = textSurface.get_rect()
            textRect.center = ((screenWidth/2), screenHeight/2)
            winMessage = screen.blit(textSurface, textRect)
        else:
            # Author: Donovan Jenkins
            # Purpose: Only advance the local ball physics when there are two active players
            #       and this client is not behind the server's max sync value.
            # Pre: server state must be receiving updates from the server and num players
            #       and max sync must be set correctly by the server thread.
            # Post: The client advances the ball and handles scoring, paddle hits, and wall
            #       bounces only when it is caught up in time, which reduces desynchronization
            #       between the two players.

            # ball logic
            if not isSpectator and server_state["num_players"] == 2: #Ensure there are two players at start of game
                with state_lock:
                    server_sync = server_state["max_sync"] #Save max sync from server
                
                if sync >= server_sync: #If the current sync is higher than the server synce, use normal game logic
                    ball.updatePos()

                    #if the ball makes it past the edge of the screen
                    if ball.rect.x > screenWidth:
                        lScore += 1
                        pointSound.play()
                        ball.reset(nowGoing="left")
                    elif ball.rect.x < 0:
                        rScore += 1
                        pointSound.play()
                        ball.reset(nowGoing="right")
                    
                    #if the ball hits a paddle
                    if ball.rect.colliderect(playerPaddleObj.rect):
                        bounceSound.play()
                        ball.hitPaddle(playerPaddleObj.rect.center[1])
                    elif ball.rect.colliderect(opponentPaddleObj.rect):
                        bounceSound.play()
                        ball.hitPaddle(opponentPaddleObj.rect.center[1])
                    
                    #if the ball hits a wall
                    if ball.rect.colliderect(topWall) or ball.rect.colliderect(bottomWall):
                        bounceSound.play()
                        ball.hitWall()
            
            pygame.draw.rect(screen, WHITE, ball.rect)
        # Author: Donovan Jenkins
        # Purpose: Blend the server's authoritative state into the local game so that the
        #          opponent paddle, ball, and scores stay synchronized across both clients.
        # Pre: server state must have been updated in the recv loop thread and the client
        #       must still be connected to the server.
        # Post: Spectators always mirror the server's state, while players update only the
        #       opponent paddle and correct their own ball and scores when they fall behind
        #       the server's max_sync value. Local scores are also clamped upward so the UI
        #       always shows the most recent totals.

        # apply latest state from server on top of local logic
        
        if client is not None:
            
            with state_lock:
                 s = server_state.copy()

            # For players: use server state only for the opponent
            if playerPaddle == "left":
                #Set opponents paddle (Right side)
                if s["right_paddle_y"] is not None:
                    rightPaddle.rect.y = int(s["right_paddle_y"])
            elif playerPaddle == "right":
                #Set opponents paddle (Left side)
                if s["left_paddle_y"] is not None:
                    leftPaddle.rect.y = int(s["left_paddle_y"])
            else:
                #Set both paddles
                if s["left_paddle_y"] is not None:
                    leftPaddle.rect.y = int(s["left_paddle_y"])
                if s["right_paddle_y"] is not None:
                    rightPaddle.rect.y = int(s["right_paddle_y"])
                    
            #Update ball and scores from server if values are present
            if isSpectator: #If its a spectator pull all values from the server to update
                if s["ball_x"] is not None:
                    ball.rect.x = s["ball_x"]
                if s["ball_y"] is not None:
                    ball.rect.y = s["ball_y"]
                if s["left_score"] is not None:
                    lScore = s["left_score"]
                if s["right_score"] is not None:
                    rScore = s["right_score"]
            
            else: #If they are a player, check if the sync is behind the server, if so use server data to update
                server_sync = s["max_sync"]
                if sync < server_sync:
                    ball.rect.x = s["ball_x"]
                    ball.rect.y = s["ball_y"]
                    lScore = s["left_score"]
                    rScore = s["right_score"]
                    sync = server_sync
            
            #Ensure both scores are as up to date as possible
            if s["left_score"] is not None and s["left_score"] > lScore:
                lScore = s["left_score"]
            if s["right_score"] is not None and s["right_score"] > rScore:
                rScore = s["right_score"]


        # drawing the dotted line in the center
        for i in centerLine:
            pygame.draw.rect(screen, WHITE, i)
        
        #drawing the player's new location
        for paddle in [playerPaddleObj, opponentPaddleObj]:
            pygame.draw.rect(screen, WHITE, paddle)

        pygame.draw.rect(screen, WHITE, topWall)
        pygame.draw.rect(screen, WHITE, bottomWall)
        scoreRect = updateScore(lScore, rScore, screen, WHITE, scoreFont)
        pygame.display.flip() #Force a buffer refresh
        clock.tick(60)
        
        # This number should be synchronized between you and your opponent.  If your number is larger
        # then you are ahead of them in time, if theirs is larger, they are ahead of you, and you need to
        # catch up (use their info)
        sync += 1

# This is where you will connect to the server to get the info required to call the game loop.  Mainly
# the screen width, height and player paddle (either "left" or "right")
# If you want to hard code the screen's dimensions into the code, that's fine, but you will need to know
# which client is which
# Author: Nebojsa Simic
# Purpose: Connect to the Pong server, receive the initial configuration (screen size
#           and paddle side), start the background receive thread, and then launch the
#           Pygame loop with the correct role for this client.
# Pre:  User must enter a valid server IP and port and the server must be listening
#       and ready to send an initial JSON config message.
# Post: On success, the Tkinter lobby window is hidden, a TCP connection is established,
#       recv_loop begins running in a separate thread, and playGame starts using the
#       dimensions and paddle side provided by the server.

def joinServer(ip:str, port:str, errorLabel:tk.Label, app:tk.Tk) -> None:
    # Purpose:      This method is fired when the join button is clicked
    # Arguments:
    # ip            A string holding the IP address of the server
    # port          A string holding the port the server is using
    # errorLabel    A tk label widget, modify it's text to display messages to the user (example below)
    # app           The tk window object, needed to kill the window
    
    # Create a socket and connect to the server
    # You don't have to use SOCK_STREAM, use what you think is best
    # create TCP socket
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    #get the required information from your server (screen width, height & player paddle, "left or "right")
    try:
        client.connect((ip, int(port)))
        init_raw = client.recv(1024)
        init_data = json.loads(init_raw.decode("utf-8"))

        screenWidth = int(init_data["screen_width"])
        screenHeight = int(init_data["screen_height"])
        paddleSide = init_data["paddle"]

        # start background receive thread
        t = threading.Thread(target=recv_loop, args=(client,))
        t.daemon = True
        t.start()

        # If you have messages you'd like to show the user use the errorLabel widget like so
        errorLabel.config(text=f"Connected. You are: {paddleSide}")
        errorLabel.update()

        # Close this window and start the game with the info passed to you from the server
        app.withdraw()
        playGame(screenWidth, screenHeight, paddleSide, client)
        app.quit()

    except Exception as e:
        errorLabel.config(text=f"Connection failed: {e}")
        errorLabel.update()
        client.close()
        return

    # Get the required information from your server (screen width, height & player paddle, "left or "right")

# This displays the opening screen, you don't need to edit this (but may if you like)
    # Author: Nebojsa Simic
    # Purpose: Load and display the project logo on the join screen using a path
    #           and a persistent Tkinter image reference to avoid garbage collection.
    # Pre: The assets folder must exist with logo.png at the expected relative path.
    # Post: The window shows the logo image correctly on all platforms without the image
    #       disappearing during runtime.

def startScreen():
    app = tk.Tk()
    app.title("Server Info")

    img_path = Path(__file__).resolve().parents[1] / "pong" / "assets" / "images" / "logo.png"
    img = Image.open(img_path)

    pil_img = Image.open(img_path)
    image = ImageTk.PhotoImage(pil_img)
    app.logo_image = image  # keep reference so it isn't GC'ed
    titleLabel = tk.Label(app, image=image)

    titleLabel = tk.Label(app, image=image)
    titleLabel.grid(column=0, row=0, columnspan=2)

    ipLabel = tk.Label(app, text="Server IP:")
    ipLabel.grid(column=0, row=1, sticky="W", padx=8)

    ipEntry = tk.Entry(app)
    ipEntry.grid(column=1, row=1)

    portLabel = tk.Label(app, text="Server Port:")
    portLabel.grid(column=0, row=2, sticky="W", padx=8)

    portEntry = tk.Entry(app)
    portEntry.grid(column=1, row=2)

    errorLabel = tk.Label(app, text="")
    errorLabel.grid(column=0, row=4, columnspan=2)

    joinButton = tk.Button(app, text="Join", command=lambda: joinServer(ipEntry.get(), portEntry.get(), errorLabel, app))
    joinButton.grid(column=0, row=3, columnspan=2)

    app.mainloop()
if __name__ == "__main__":
    startScreen()
    

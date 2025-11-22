# =================================================================================================
# Contributing Authors:	    <Anyone who touched the code>
# Email Addresses:          <Your uky.edu email addresses>
# Date:                     <The date the file was last edited>
# Purpose:                  <How this file contributes to the project>
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

# simple shared state from server
server_state = {
    "left_paddle_y": None,
    "right_paddle_y": None,
    "ball_x": None,
    "ball_y": None,
    "left_score": None,
    "right_score": None
}
state_lock = threading.Lock()

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

            # ball logic
            if not isSpectator:
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
            
            pygame.draw.rect(screen, WHITE, ball)

        # apply latest state from server on top of local logic
        if client is not None:
            with state_lock:
                s = server_state.copy()

            # update paddles from server if values are present
            if s["left_paddle_y"] is not None:
                leftPaddle.rect.y = int(s["left_paddle_y"])
            if s["right_paddle_y"] is not None:
                rightPaddle.rect.y = int(s["right_paddle_y"])

            # update ball and scores from server if values are present
            if s["ball_x"] is not None:
                ball.rect.x = int(s["ball_x"])
            if s["ball_y"] is not None:
                ball.rect.y = int(s["ball_y"])
            if s["left_score"] is not None:
                lScore = int(s["left_score"])
            if s["right_score"] is not None:
                rScore = int(s["right_score"])

        # drawing the dotted line in the center
        for i in centerLine:
            pygame.draw.rect(screen, WHITE, i)
        
        #drawing the player's new location
        for paddle in [playerPaddleObj, opponentPaddleObj]:
            pygame.draw.rect(screen, WHITE, paddle)

        pygame.draw.rect(screen, WHITE, topWall)
        pygame.draw.rect(screen, WHITE, bottomWall)
        scoreRect = updateScore(lScore, rScore, screen, WHITE, scoreFont)
        pygame.display.update([topWall, bottomWall, ball, leftPaddle, rightPaddle, scoreRect, winMessage])
        clock.tick(60)
        
        # This number should be synchronized between you and your opponent.  If your number is larger
        # then you are ahead of them in time, if theirs is larger, they are ahead of you, and you need to
        # catch up (use their info)
        sync += 1

# This is where you will connect to the server to get the info required to call the game loop.  Mainly
# the screen width, height and player paddle (either "left" or "right")
# If you want to hard code the screen's dimensions into the code, that's fine, but you will need to know
# which client is which
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
def startScreen():
    app = tk.Tk()
    app.title("Server Info")

    img_path = Path(__file__).resolve().parent / "assets" / "images" / "logo.png"

    pil_img = Image.open(img_path)
    image = ImageTk.PhotoImage(pil_img)
    app.logo_image = image  # keep reference so it isn't GC'ed
    titleLabel = tk.Label(app, image=image)

    #titleLabel = tk.Label(image=image)
    titleLabel.grid(column=0, row=0, columnspan=2)

    ipLabel = tk.Label(text="Server IP:")
    ipLabel.grid(column=0, row=1, sticky="W", padx=8)

    ipEntry = tk.Entry(app)
    ipEntry.grid(column=1, row=1)

    portLabel = tk.Label(text="Server Port:")
    portLabel.grid(column=0, row=2, sticky="W", padx=8)

    portEntry = tk.Entry(app)
    portEntry.grid(column=1, row=2)

    errorLabel = tk.Label(text="")
    errorLabel.grid(column=0, row=4, columnspan=2)

    joinButton = tk.Button(text="Join", command=lambda: joinServer(ipEntry.get(), portEntry.get(), errorLabel, app))
    joinButton.grid(column=0, row=3, columnspan=2)

    app.mainloop()
if __name__ == "__main__":
    startScreen()
    
    # Uncomment the line below if you want to play the game without a server to see how it should work
    # the startScreen() function should call playGame with the arguments given to it by the server this is
    # here for demo purposes only
    playGame(640, 480,"left",socket.socket(socket.AF_INET, socket.SOCK_STREAM))

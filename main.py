from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from bson import ObjectId
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from starlette.requests import Request
import json
from typing import Dict, List, Optional, Any


app = FastAPI()
app.add_middleware(
   CORSMiddleware,
   allow_origins=["*"],
   allow_credentials=True,
   allow_methods=["*"],
   allow_headers=["*"],
)
templates = Jinja2Templates(directory="templates")
client = MongoClient("mongodb://localhost:27017/")
db = client.chat_db

class ConnectionManager:
   def __init__(self):
       self.active_connections: Dict[str, List[WebSocket]] = {}

   async def connect(self, websocket: WebSocket, username: str):
       await websocket.accept()
       if username in self.active_connections:
           self.active_connections[username].append(websocket)
       else:
           self.active_connections[username] = [websocket]

   def disconnect(self, websocket: WebSocket, username: str):
       if username in self.active_connections:
           self.active_connections[username].remove(websocket)
           if not self.active_connections[username]:
               del self.active_connections[username]

   async def send_personal_message(self, message: str, sender: str, receiver: str):
       if receiver in self.active_connections:
           for connection in self.active_connections[receiver]:
               await connection.send_json(message)
         
       if sender in self.active_connections:
           for connection in self.active_connections[sender]:
               await connection.send_json(message)
         
   async def broadcast(self, message: str):
       for connections in self.active_connections.values():
           for connection in connections:
               await connection.send_json(message)

manager = ConnectionManager()

@app.websocket("/chat/{username}/{receiver}")
async def chat_endpoint(websocket: WebSocket, username: str, receiver: str):
   print("webbbb")
   await manager.connect(websocket, username)
   try:
       while True:
           data = await websocket.receive_json()
           print("data",data)

           message_id = data.get('id')
           action = data.get('action')

           print(action,"message_id",message_id)
           if action == 'delete':
               print("del")
               if message_id:
                   # Delete the message if an _id is provided and action is delete
                   db.messages.delete_one({"_id": ObjectId(message_id)})
                   # Broadcast the delete action to all connections
                   delete_message_data = {"_id": message_id, "action": "delete"}
                   print('11111111111',delete_message_data,username,receiver)
                   await manager.send_personal_message(delete_message_data, username, receiver)
           elif message_id:
               print("edittt")

               # Update the message if an _id is provided and action is not delete
               result = db.messages.update_one(
                   {'_id': ObjectId(message_id)},
                   {'$set': {'message': data['message']}},
                 
               )
               data['sender'] = username
               data['receiver'] = receiver
               data['_id'] = message_id  # Send back the existing ID
               # Broadcast the updated message to all connections
               print(result,'2222222222222',data,username,receiver)

               await manager.send_personal_message(data, username, receiver)
           else:
               print("newww")

               # Insert a new message if no _id is provided
               data['sender'] = username
               data['receiver'] = receiver
               result = db.messages.insert_one(data)
               data['_id'] = str(result.inserted_id)

               # Send the message to the intended receiver
               await manager.send_personal_message(data, data["sender"], data["receiver"])
   except WebSocketDisconnect:
       manager.disconnect(websocket, username)

@app.get("/users")
async def get_users():
   # Replace this with your actual user fetching logic from your database
   users = db.Users.find({}, {"_id": 0, "user_name": 1})
   return [user['user_name'] for user in users]

@app.get("/chat_history/{username}/{receiver}")
async def get_chat_history(username: str, receiver: str):
   # Fetch chat history between two users
   chat_history = db.messages.find({
       "$or": [
           {"sender": username, "receiver": receiver},
           {"sender": receiver, "receiver": username}
       ]
   }).sort("_id", -1).limit(50)
   result = []
   for msg in chat_history:
       try:
           message = msg.get('message', '')  # Default to empty string if 'message' is missing
           sender = msg.get('sender', 'Unknown')  # Default to 'Unknown' if 'sender' is missing
           msg_id = str(msg.get('_id', ''))  # Ensure '_id' is converted to string

           result.append({"message": message, "sender": sender, "id": msg_id})
       except Exception as e:
           logging.error(f"Error processing message: {msg}. Error: {e}")
   print("result",result)
   return result

# First page
@app.get('/')
async def getChat():
   messages =  db.messages.find()
   users =  db.Users.find()

   # Convert ObjectId to string for front-end
   for message in messages:
       message['_id'] = str(message['_id'])
       print("mouniiiiiii--", message['_id'])
     
   for user in users:
       user['_id'] = str(user['_id'])

   # Convert users list to JSON format
   # users_json = json.loads(users)

   # Select the appropriate template based on the chat type
   # template = templates.get_template('chat.html')  # For many-to-many chat room
   template = templates.get_template('single-chat.html')  # For one-to-one chat room

   rendered_template = template.render(messages=messages, users=users)
   return HTMLResponse(content=rendered_template)
 
# After login save data
@app.post("/login")
async def login(request: Request):
   data = await request.json()
   userName = data.get("user_name")
   password = data.get("password")
   print("1111111")
   user = db.Users.find_one({"user_name": userName})
   print("2222222")
   user['_id'] = str(user['_id'])

   if user:
       print("3")

       return {"message": "User found", "user": user}
   else:
       print("1111111")

       result = db.Users.insert_one({"user_name": userName, "password": password})
       user = {"user_name": userName, "password": password}
       return {"message": "User created", "user": user}

# Update Message API
@app.put("/messages/{message_id}")
async def update_message(message_id: str, request: Request):
   print("4444445555555555566666666")
   data = await request.json()
   print("data",data)
   message = data.get("message")
   if not message:
       raise HTTPException(status_code=400, detail="Message content is required")

   result = db.messages.update_one(
       {"_id": ObjectId(message_id)},
       {"$set": {"message": message}}
   )

   if result.matched_count == 0:
       raise HTTPException(status_code=404, detail="Message not found")

   return {"message": "Message updated successfully"}

# Delete Message API
@app.delete("/messages/{message_id}")
async def delete_message(message_id: str):
   result = db.messages.delete_one({"_id": ObjectId(message_id)})
   print(message_id,"result---",result)
   print("result---",result.deleted_count )
   messages =  db.messages.find()
   for message in messages:
       message['_id'] = str(message['_id'])
       print("messages--", message['_id'])
   if result.deleted_count == 0:
       raise HTTPException(status_code=404, detail="Message not found")

   return {"message": "Message deleted successfully"}

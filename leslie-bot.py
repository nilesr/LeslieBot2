#!/usr/bin/env python3
import discord, asyncio, re
import threading, time, requests, json, BTEdb, hashlib, io, string
import websocket, functools, base36, queue, uuid, logging, sys
# websocket.enableTrace(True)
from PIL import Image

API_BASE = "https://api.groupme.com/v3"

db = BTEdb.Database("leslie-bot-cache.json")
if not db.TableExists("main"): db.CreateTable("main")
if not db.TableExists("macros"): db.CreateTable("macros")

groupme_user_id = 99999999
groupme_access_token = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

mirrors = [
    {
      "groupme_group_id": 99999999,
      "discord_guild_id": 999999999999999999,
      "discord_channel_id": 999999999999999999,
      },
    {
      "groupme_group_id": 99999999,
      "discord_guild_id": 999999999999999999,
      "discord_channel_id": 999999999999999999,
      },
    ]

groupme_send_buffer = queue.Queue()

heart = "❤"

client = discord.Client()

recent_messages = [[]] * len(mirrors)

logging.basicConfig(format="%(asctime)-15s %(message)s", level=logging.INFO, stream=sys.stdout)
log = logging.getLogger("leslie-bot-2")

log.info('------')
log.info("Logging in now...")

def guid():
  return uuid.uuid4().hex 

def get_server_by_discord_channel_id(id):
  for i, mirror in enumerate(mirrors):
    if mirror["discord_channel_id"] == id:
      log.debug("discord channel {} => server {}".format(id, i))
      return i
  log.debug("discord channel {} => server {}".format(id, -1))
  return -1

def get_server_from_groupme_group_id(id):
  id = int(id)
  for i, mirror in enumerate(mirrors):
    if mirror["groupme_group_id"] == id:
      log.debug("groupme group {} => server {}".format(id, i))
      return i
  log.debug("groupme group {} => server {}".format(id, -1))
  return -1

def register_message(server, discord_id, groupme_id, groupme_source_guid):
  global recent_messages
  if server < 0:
    log.error("register_message got invalid server {}".format(server))
    return
  recent_messages[server].insert(0, {
    "discord_id": discord_id,
    "groupme_id": groupme_id,
    "groupme_source_guid": groupme_source_guid,
    "has_discord_favorites": False,
    })
  recent_messages[server] = recent_messages[server][:40]
  log.debug("Registered message with IDs {}, {}, {}".format(discord_id, groupme_id, groupme_source_guid))

async def add_macro(server, text, url):
  matchdata = re.search("#add_macro ([^ ]*)", text)
  if not matchdata:
    err = "Failed to find new macro name in message '{}'".format(text)
    log.error(err)
    await inject_message(server, err, False)
    return
  name = matchdata.group(1)
  if len(db.Select("macros", name = name)) > 0:
    err = "Stubbornly refusing to overwrite existing macro {} to new url {}".format(name, url)
    log.error(err)
    await inject_message(server, err, False)
    return
  log.info("Added new macro {} url {}".format(name, url))
  db.Insert("macros", name = name, url = url)

def get_macro_url(text):
  matchdata = re.search("#m ([^ ]*)", text)
  if not matchdata:
    err = "Failed to find macro name in message '{}'".format(text)
    log.error(err)
    return False, err
  name = matchdata.group(1)
  results = db.Select("macros", name = name)
  if len(results) == 0:
    err = "Failed to find macro with name {} in message '{}'".format(name, text)
    log.error(err)
    return False, err
  return True, results[0]["url"]

async def handle_macro(server, text, attachments):
  attachments = [a for a in attachments if a["type"] == "image"]
  url = False
  if len(attachments) > 0:
    url = attachments[0]["url"]
  if "#add_macro" in text:
    if not url:
      await inject_message(server, "No attachment?", False)
      return
    await add_macro(server, text, url)
    return
  if re.search("#m [^ ]*", text):
    status, url = get_macro_url(text)
    if status:
      await inject_message(server, "", url)
    else:
      await inject_message(server, url, False)

async def inject_message(server, text, url):
  channel = client.get_channel(mirrors[server]["discord_channel_id"])
  e = None
  if url:
    e = discord.Embed()
    e.set_image(url = url)
  m = await channel.send(text, embed = e);
  data = {
      "text": text,
      "source_guid": guid(),
      }
  if url:
    data["attachments"] = [{"type": "image", "url": url}]
  groupme_send_buffer.put([server, m.id, json.dumps({"message": data})])
  # groupme send thread will call register_message


@client.event
async def on_ready():
  log.info('Logged in as')
  log.info(client.user.name)
  log.info(client.user.id)
  log.info('------')

def upload(url):
  log.debug("Downloading from: " + url)
  data = requests.get(url)
  log.debug("Response: " + str(data))
  r = requests.post("https://image.groupme.com/pictures", files = {'file': data.content}, headers = {"X-Access-Token": groupme_access_token})
  log.debug(r)
  j = json.loads(r.text)
  return j["payload"]["url"] + ".large"

def apply_format(text, alphabet):
  base = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
  result = ""
  for c in text:
    idx = base.find(c)
    if idx >= 0:
      result += alphabet[idx]
    else:
      result += c
  return result
def bold_italic(k): return apply_format(k, "𝙖𝙗𝙘𝙙𝙚𝙛𝙜𝙝𝙞𝙟𝙠𝙡𝙢𝙣𝙤𝙥𝙦𝙧𝙨𝙩𝙪𝙫𝙬𝙭𝙮𝙯𝘼𝘽𝘾𝘿𝙀𝙁𝙂𝙃𝙄𝙅𝙆𝙇𝙈𝙉𝙊𝙋𝙌𝙍𝙎𝙏𝙐𝙑𝙒𝙓𝙔𝙕")
def bold(k): return apply_format(k, "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭")
def italic(k): return apply_format(k, "𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡")
def underline(k): return apply_format(k, list(map(lambda c: c + chr(0x332), string.ascii_letters)))
def strikethrough(k): return apply_format(k, list(map(lambda c: c + chr(0x336), string.ascii_letters)))

def format(text):
  split = re.split('(~~[^~]*~~|___[^_]*___|__[^_]*__|_[^_]*_|\\*\\*\\*[^\\*]*\\*\\*\\*|\\*\\*[^\\*]*\\*\\*|\\*[^\\*]*\\*)', text)
  result = ""
  for k in split:
    if k.startswith("***") and k.endswith("***"):
      result += bold_italic(k[3:-3])
    elif k.startswith("**") and k.endswith("**"):
      result += bold(k[2:-2])
    elif k.startswith("*") and k.endswith("*"):
      result += italic(k[1:-1])
    elif k.startswith("___") and k.endswith("___"):
      result += underline(italic(k[3:-3]))
    elif k.startswith("__") and k.endswith("__"):
      result += underline(k[2:-2])
    elif k.startswith("_") and k.endswith("_"):
      result += italic(k[1:-1])
    elif k.startswith("~~") and k.endswith("~~"):
      result += strikethrough(k[2:-2])
    else:
      result += k
  return result

# TODO clean up
def extract_emoji_id(emoji_id):
  return int(emoji_id.split(":")[2].replace(">", ""))

# key, user_id, emoji_id
async def get_emoji(server, key, user_id, display_name):
  results = db.Select("main", key = key);
  if len(results) == 1:
    return results[0]["emoji_id"]
  guild = client.get_guild(mirrors[server]["discord_guild_id"])
  old_emoji = db.Select("main", user_id = user_id)
  if len(old_emoji) > 0:
    e = client.get_emoji(extract_emoji_id(old_emoji[0]["emoji_id"]))
    if e:
      log.info("Deleting emoji " + str(e))
      await e.delete(reason = "User " + user_id + ", " + display_name + " has new profile picture")
    db.Delete("main", user_id = user_id)
  try:
    name = hashlib.md5(key.encode("utf-8")).hexdigest()[:6]
    log.info("Creating emoji " + name + " for user "+user_id+", "+display_name+" with image from " + key)
    data = requests.get(key)
    log.info("Got {} bytes of content".format(len(data.content)))
    image = Image.open(io.BytesIO(data.content))
    image = image.resize((32, 32), Image.ANTIALIAS)
    resized = io.BytesIO()
    image.save(resized, format='PNG')
    log.debug(len(resized.getvalue()));
    emoji = await guild.create_custom_emoji(name = name , image = resized.getvalue(), reason = "Leslie-Bot: New avatar for user ID " + user_id + ", name: " + display_name)
    emoji_id = "<:{}:{}>".format(name, emoji.id);
    db.Insert("main", key = key, user_id = user_id, emoji_id = emoji_id);
    return emoji_id
  except Exception as e:
    log.exception(e)
    return ""

def get_emoji_simple(user_id):
  results = db.Select("main", user_id = user_id);
  if len(results) == 1:
    return extract_emoji_id(results[0]["emoji_id"])
  return None

@client.event
async def on_message(message):
  if message.author.bot:
    log.debug("DISCARDING BOT MESSAGE FROM ", message.author)
    return
  server = -1
  if message.channel:
    server = get_server_by_discord_channel_id(message.channel.id)
  if not message.channel or server == -1:
    log.debug("Discarding message from " + str(message.channel));
    return
  while True:
    m = re.search("<@!?([0-9]*)>", message.content)
    if not m: break
    user = message.channel.guild.get_member(int(m.group(1)))
    message.content = message.content.replace(m.group(0), "@" + user.display_name)
  while True:
    m = re.search("<:([^:]*):\d+>", message.content)
    if not m: break
    message.content = message.content.replace(m.group(0), "(" + m.group(1) + " emoji)")
  data = {
      "text": message.author.display_name + ": " + format(message.content),
      "attachments": [
        #{"type": "image", "url": "https://i.groupme.com/512x512.jpeg.cef5c0012cb846819203fb81d9ccb4ed"}
        ],
      "source_guid": guid(),
      }
  for em in message.attachments:
    data["attachments"].append({"type": "image", "url": upload(em.url)})

  # data["text"] = data["text"].replace("%", chr(0x200b) + "0⁄0" + chr(0x200b));
  groupme_send_buffer.put([server, message.id, json.dumps({"message": data})])
  await handle_macro(server, message.content, data["attachments"])


def favorite_message(server, id):
  r = requests.post("{}/messages/{}/{}/like".format(API_BASE, mirrors[server]["groupme_group_id"], id), headers = {"X-Access-Token": groupme_access_token})
  if r.status_code != 200:
    log.error("Error favoriting message {}. Status {}, response: {}".format(id, r.status_code, r.text))

def unfavorite_message(server, id):
  r = requests.post("{}/messages/{}/{}/unlike".format(API_BASE, mirrors[server]["groupme_group_id"], id), headers = {"X-Access-Token": groupme_access_token})
  if r.status_code != 200:
    log.error("Error unfavoriting message {}. Status {}, response: {}".format(id, r.status_code, r.text))

@client.event
async def on_reaction_add(reaction, user):
  channel = reaction.message.channel
  server = -1
  if channel:
    server = get_server_by_discord_channel_id(channel.id)
  if server == -1:
    log.debug("Ignoring reaction_add to message in {}".format(channel))
    return
  try:
    m = next(x for x in recent_messages[server] if x["discord_id"] == reaction.message.id)
  except Exception as e:
    log.error("Message with discord id {} not found in recent_messages".format(id))
    return
  reaccs = [r for r in reaction.message.reactions if not (r.me and r.count == 1) and r.emoji == heart]
  has_discord_favorites = len(reaccs) > 0
  log.debug(reaccs)
  log.debug("before: {}, after: {}".format(m["has_discord_favorites"], has_discord_favorites))
  if has_discord_favorites == m["has_discord_favorites"]:
    return
  if has_discord_favorites and not m["has_discord_favorites"]:
    favorite_message(server, m["groupme_id"])
  else:
    unfavorite_message(server, m["groupme_id"])
  m["has_discord_favorites"] = has_discord_favorites

@client.event
async def on_reaction_remove(reaction, user):
  await on_reaction_add(reaction, user)

async def update_discord_likes_from_groupme(server, users, id, source_guid):
  try:
    m = next(x for x in recent_messages[server] if x["groupme_id"] == id and x["groupme_source_guid"] == source_guid)
  except Exception:
    log.error("Message with groupme ids {}, {} not found in recent_messages".format(id, source_guid))
    return
  users = list(filter(lambda user: int(user) != groupme_user_id, users)) # filter out myself
  m = await client.get_channel(mirrors[server]["discord_channel_id"]).fetch_message(m["discord_id"])
  reaccs = [r for r in m.reactions if r.me]
  needed = set(filter(None, (get_emoji_simple(user) for user in users)))
  needed = [client.get_emoji(n) for n in needed]
  if len(users) > 0:
    needed.insert(0, heart) # heart always comes first
  for r in reaccs:
    if not r.emoji in needed:
      await r.remove()
    else:
      needed.remove(r.emoji)
  for e in needed:
    await m.add_reaction(e)

async def RecvMessage(s):
  server = get_server_from_groupme_group_id(s["group_id"])
  mirror = mirrors[server]
  channel = client.get_channel(mirror["discord_channel_id"])
  if s["sender_type"] == "bot":
    log.debug("RecvMessage discarding bot message from sender {}".format(s["sender_id"]))
    return
  nickname = s["name"]
  e = None
  for attachment in s["attachments"]:
    if attachment["type"] == "image":
      e = discord.Embed()
      e.set_image(url = attachment["url"])
  emoji = await get_emoji(server, s["avatar_url"], s["sender_id"], s["name"]) if s["sender_id"] != "system" else ""
  if not s["text"]:
    s["text"] = ""
  m = await channel.send(emoji + "**" + nickname + "**: " + s["text"], embed = e);
  register_message(server, m.id, int(s["id"]), s["source_guid"])
  await handle_macro(server, s["text"], s["attachments"])

client_loop = asyncio.get_event_loop()


class GroupmeConnection():
  def __init__(self, client_id):
    self.id = 1
    self.client_id = client_id
    log.info("Opening websocket")
    def f1(f2):
      def f3(*args, **kwargs):
        try:
          return f2(*args, **kwargs)
        except Exception as e:
          log.error("failed to call function {} with arguments {}, {}".format(f2, args, kwargs))
          log.exception(e)
          raise e
      return f3

    wrap = lambda f: f1(functools.partial(f))
    self.ws = websocket.WebSocketApp("wss://push.groupme.com/faye",
        on_message = wrap(self.on_message),
        on_error = wrap(self.on_error),
        on_open = wrap(self.on_open))

  def run_forever(self):
    self.ws.run_forever()

  def bump_id(self):
    self.id += 1
    return base36.dumps(self.id)

  def ext(self):
    return {
        "access_token": groupme_access_token,
        "timestamp": int(time.time())
        }

  def subscribe(self, ws, subscription):
    message = {
        "channel": "/meta/subscribe",
        "clientId": self.client_id,
        "subscription": subscription,
        "id": self.bump_id(),
        "ext": self.ext()
        }
    log.info("Sending subscribe request to {}".format(subscription))
    ws.send(json.dumps([message]))

  def send_connect(self, ws):
    message = {
        "channel": "/meta/connect",
        "clientId": self.client_id,
        "connectionType": "websocket",
        "id": self.bump_id(),
        }
    log.info("Sending connect request")
    ws.send(json.dumps([message]))

  def send_ping(self, ws, channel):
    message = {
        "channel": channel,
        "clientId": self.client_id,
        "id": self.bump_id(),
        # "data": {"type": "ping"},
        "successful": True,
        "ext": self.ext()
        }
    log.debug("Sending ping response on channel {}".format(channel))
    ws.send(json.dumps([message]))

  def on_open(self, ws):
    log.info("Socket open")
    self.subscribe(ws, "/user/{}".format(groupme_user_id))
    for mirror in mirrors:
      self.subscribe(ws, "/group/{}".format(mirror["groupme_group_id"]))
    self.send_connect(ws)

  def on_message(self, ws, message):
    message = json.loads(message)
    for m in message:
      try:
        if base36.loads(m["id"]) > self.id:
          self.id = base36.loads(m["id"])
      except:
        log.warning("Funky ID (non-base36) on message {}".format(json.dumps(m, indent = 4)))

      if "data" in m and m["data"]["type"] == "ping":
        self.send_ping(ws, m["channel"])
      elif m["channel"] == "/meta/connect" and m["successful"]:
        time.sleep(m["advice"]["interval"]) # always zero so whatever
        self.send_connect(ws)
      elif "data" in m and m["data"]["type"] == "line.create":
        d = m["data"]["subject"]
        server = get_server_from_groupme_group_id(d["group_id"])
        if server == -1:
          log.debug("Groupme discarding message to unknown group {}".format(d["group_id"]))
          return
        if d["sender_id"] != "system" and int(d["sender_id"]) == groupme_user_id:
          log.debug("Groupme discarding self message")
          return
        coro = RecvMessage(d)
        future = asyncio.run_coroutine_threadsafe(coro, client_loop)
        future.result()
      elif "data" in m and m["data"]["type"] == "like.create":
        # these appear to be duplicated with the "favorite" messages
        pass
      elif "data" in m and m["data"]["type"] == "favorite":
        d = m["data"]["subject"]["line"]
        log.debug("Got favorite call")
        server = get_server_from_groupme_group_id(d["group_id"])
        coro = update_discord_likes_from_groupme(server, d["favorited_by"], int(d["id"]), d["source_guid"])
        future = asyncio.run_coroutine_threadsafe(coro, client_loop)
        future.result()
      elif "data" not in m and m.get("successful", False) and m["channel"] == "/user/{}".format(groupme_user_id):
        # probably a ping response
        pass
      elif "data" not in m and m.get("successful", False) and m["channel"] == "/meta/subscribe":
        # subscription success
        log.info("Subscription success to {}".format(m["subscription"]))
      else:
        log.warning("Groupme got unhandled message: {}".format(json.dumps(message, indent = 4)))

  def on_error(self, ws, error):
    log.error("Websocket error: {}".format(error))


def groupme_recv_thread():
  while True:
    try:
      handshake = {
          "channel": "/meta/handshake",
          "version": "1.0",
          "supportedConnectionTypes": ["long-polling"], # ????
          "id": "1"
          }
      r = requests.get("https://push.groupme.com/faye", params={"message": json.dumps([handshake]), "jsonp": "callback"})
      faye_client_id = json.loads(r.text[4 + len("callback") + 1:-2])[0]["clientId"]
      log.info("Got faye connection id {}".format(faye_client_id))
      gc = GroupmeConnection(faye_client_id)
      gc.run_forever()
    except Exception as e:
      log.exception(e)
      time.sleep(1)

def groupme_send_thread():
  while True:
    item = groupme_send_buffer.get() 
    try:
      mirror = mirrors[item[0]]
      r = requests.post("{}/groups/{}/messages".format(API_BASE, mirror["groupme_group_id"]), data = item[2], headers = {"X-Access-Token": groupme_access_token, "Content-Type": "application/json;charset=UTF-8"})
      if r.status_code != 201:
        log.error("Failed to upload item, status code {}: {}\n{}".format(r.status_code, json.dumps(json.loads(item[2]), indent=4), r.text))
      else:
        discord_id = item[1]
        groupme_id = int(r.json()["response"]["message"]["id"])
        source_guid = r.json()["response"]["message"]["source_guid"]
        register_message(item[0], discord_id, groupme_id, source_guid)
    except Exception as e:
      log.exception(e)


t = threading.Thread(target = groupme_recv_thread)
t.start();

t = threading.Thread(target = groupme_send_thread)
t.start();

# assuming that this line calls asyncio run_forever()
client.run("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")

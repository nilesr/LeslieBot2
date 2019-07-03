## LeslieBot 2 is a GroupMe ↔ Discord bridge

![](ss.png)

## Differences from LeslieBot

LeslieBot operates as a bot user in GroupMe. The GroupMe bot API only allows you to send and recieve messages. It does not allow you to send likes, or view who has liked an existing message. It also only allows you to recieve messages via an HTTP post-back, requiring you to run your own http server, and in the case of LeslieBot-1, `mako-server` with `dbus`. 

LeslieBot 2 allows runs as a normal user, and can recieve messages over websocket, and like groupme messages and see who else has liked groupme messages. Most of the discord-specific code is the same from LeslieBot, but the groupme interface has been rewritten from scratch.

### Set Up

Install prerequisites: discord.py **rewrite branch**, `base36`, `websocket-client` (not `websocket`), `BTEdb` and `pillow`

In the developer portal for Discord, create a discord bot. Put your discord bot access token in the `client.run` call at the bottom of `leslie-bot.py`, and put the guild id and channel id in the variables at the top.

Create a new GroupMe account and join the group you would like to mirror. Go to the develoepr portal and obtain an access token. Put your personal GroupMe access token, GroupMe user ID, and the ID of the group you would like to mirror in the variables at the top of `leslie-bot.py`.

Add the Discord bot to the right guild. The discord bot wants permission to view channels, read messages, send messages, send messages with embeds and images, add reactions, and **manage custom emoji** (see the emoji section).

### Running

Just run `leslie-bot.py`. It will connect to Discord and GroupMe, with one main thread and two background threads.

When a discord message is received, it will tell the second background thread to POST a message to the GroupMe user API to send that message to the GroupMe channel. If the post contains an uploaded image, it will download the image and re-upload it to the GroupMe image service API.

When a GroupMe message is recieved from the websocket conection, a coroutine is created to handle sending the message to discord, and the coroutine is executed on the main thread using `asyncio.run_coroutine_threadsafe`

#### Custom Emojis

The first time someone speaks in GroupMe, LeslieBot downloads their profile picture, resizes it to 32x32 and creates a custom emoji for them. If they change their profile picture, it will delete the old one and create a new one. If there are too many emojis in the guild (the default limit is 50), **it will crash**. You can replace the entirety of the `get_emoji` function with `return ""` to disable this feature, however discord users will also be unable to see which groupme users have liked the message.

If you rename the custom emojis it will probably stop working until the user changes their profile picture. This is a design deficiency, not a technical problem, because I realized there was an easier way to store and retrieve the emojis way after I implemented it, but I'm too lazy to fix it.

If a user uses a custom emoji in the discord server, like :eevee:, it sends it to groupme as "(eevee emoji)"

#### Macros

You can add a macro by sending a message with "#add\_macro somename" and an attached image. Once added, anyone can use a macro by sending a message with "#m somename" in it. Only attached images are supported right now, not URLs. Macros are also stored in the cache.

### Known bugs and mitigations

- **Formatting** Discord supports italics, bold, and italics and bold using markdown, so \*italics\* for *italics*, \*\*bold\*\* for **bold**, and \*\*\*all three\*\*\* for ***all three***. GroupMe does not support this, but the bot will attempt to use some more obscure unicode codepoints to force it, like 𝘪𝘵𝘢𝘭𝘪𝘤𝘴, 𝗯𝗼𝗹𝗱, and 𝙗𝙤𝙡𝙙 𝙞𝙩𝙖𝙡𝙞𝙘𝙨. Some people with iPhones cannot see these symbols. If that's a problem, replace the implementation of `format` with just `return text;`. It also supports discord underline (`__`), underlined italics (`___`), and strikethrough (`~~`) by using combining underline and combining strike through characters.

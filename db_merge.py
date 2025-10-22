import json

with open('db.json', 'r') as f:
    current_db = json.load(f)
    current_db = current_db['modlog']

with open('db_old.json', 'r') as f:
    old_db = json.load(f)
    old_db = old_db['modlog']
    
for guild_id in old_db:
    old_guild_data = old_db[guild_id]
    current_guild_data = current_db[guild_id]
    print(guild_id, len(old_guild_data), len(current_guild_data))
    for user_id in old_guild_data:
        if user_id not in current_guild_data:
            current_guild_data[user_id] = old_guild_data[user_id]
        else:
            for data in old_guild_data[user_id]:
                if data not in current_guild_data[user_id]:
                    current_guild_data[user_id].append(data)
    
    
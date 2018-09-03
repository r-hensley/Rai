gcloud compute instances start centos
call gcloud compute scp Rai.py ryry013@centos:/home/ryry013/bot/Rai.py
call gcloud compute scp ./cogs/owner.py ./cogs/main.py ./cogs/welcome.py ./cogs/math.py ryry013@centos:/home/ryry013/bot/cogs/
gcloud compute instances reset centos
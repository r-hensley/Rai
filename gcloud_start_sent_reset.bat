gcloud compute instances start centos
call gcloud compute scp Rai.py ryry013@centos:/home/ryry013/bot/Rai.py
all gcloud compute scp ./cogs/Owner.py ./cogs/Main.py ./cogs/Welcome.py ./cogs/Math.py ryry013@centos:/home/ryry013/bot/cogs/
gcloud compute instances reset centos
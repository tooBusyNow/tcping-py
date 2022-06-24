Authors:
- Petrov Yegor && Denis Myshinskii

Task Name:
- Tcping tool

Description:
-  Tcping tool allows you to ping hosts by sending SYN TCP packet 
   and recieving ACK TCP packet from other side. So, it doesn't need 
   to establish TCP connection for pinging.

Usage:
    Common cases:
        $sudo python3 tcping.py dns.yandex -p 53 -c 5 -i 0.5 -t 2 
        $sudo python3 tcping.py habr.ru -p 19 -c 3                  ## No responses, closed tcp port
        $sudo python3 tcping.py 87.240.190.72 -p 80 -c 10           ## 87.240.190.72 is IP for vk.com

    Regular test run: 
        $sudo python3 test_tcping.py
    
    Test run with coverage (~80%):
        $sudo python3 -m pytest --tb=line --cov=.

Structure:
	tcping.py - TCPing script itself
	test_tcping.py - tests for TCPing

	bot_logic.py - main script for Telegram Bot and Watch Dog


            ┌────────────────────────────┐
            │ Watch Dog workflow scheme  │
┌──────────────────────────────────────────────────────┐
│┌────────┐                                            │         
││ Daemon │          (Waiting 4 Response)              │ 
│├────────┴──────────────┐        ┌───────────────┐    │     
││Python TCPing Instances├<──────>│  Remote Host  │    │ 
│└──────────────┬────────┘        └───────────────┘    │       
│         (Got response)                               │
│               ↓                                      │
│              ┌─────────────┐                         │ 
│       ┌─────>│ state_files │                         │ 
│       │      └─────────────┘                         │ 
│ ┌─────┴──┐                                           │ 
│ │ Daemon │                                           │ 
│ ├────────┴───┐        ┌───────────────────┐          │ 
│ │ Watcher    │ ──────>│   Telegram User   │          │ 
│ └────────────┘        └───────────────────┘          │ 
└──────────────────────────────────────────────────────┘


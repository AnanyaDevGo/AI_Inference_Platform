@echo off
set WSL_IP=172.30.94.3

netsh interface portproxy delete v4tov4 listenport=8443 listenaddress=127.0.0.1 >nul 2>&1
netsh interface portproxy delete v4tov4 listenport=3001  listenaddress=127.0.0.1 >nul 2>&1
netsh interface portproxy delete v4tov4 listenport=8089  listenaddress=127.0.0.1 >nul 2>&1

netsh interface portproxy add v4tov4 listenport=8443 listenaddress=127.0.0.1 connectport=8443 connectaddress=%WSL_IP%
netsh interface portproxy add v4tov4 listenport=3001  listenaddress=127.0.0.1 connectport=3001  connectaddress=%WSL_IP%
netsh interface portproxy add v4tov4 listenport=8089  listenaddress=127.0.0.1 connectport=8089  connectaddress=%WSL_IP%

echo Done > C:\Users\AnanyaPradeep\AI_Inference_Platform\portproxy_done.txt

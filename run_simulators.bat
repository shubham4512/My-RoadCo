@echo off
cd /d "D:\my bus\backend"
start "Bus 1 Simulator" cmd /k python simulate_driver.py --bus-id 1 --interval 3 --api-key dev-driver-key
start "Bus 2 Simulator" cmd /k python simulate_driver.py --bus-id 2 --interval 4 --api-key dev-driver-key

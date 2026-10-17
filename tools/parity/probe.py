import sys, time, ui, pm
ui.adb("shell","input","tap","1005","367"); time.sleep(.5)
pm.type_task(sys.argv[2]); time.sleep(2.5)
ui.adb("exec-out","true")
(ui.OUT/f"probe_{sys.argv[1]}.png").write_bytes(ui.adb("exec-out","screencap","-p",binary=True))

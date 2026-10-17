import sys, time, ui, pm
pm.reset(); ui.type_keys("1"); time.sleep(1); ui.adb("shell","input","tap","1005","367"); time.sleep(1)
pm.type_task(sys.argv[2]); time.sleep(2.5)
(ui.OUT/f"probe_{sys.argv[1]}.png").write_bytes(ui.adb("exec-out","screencap","-p",binary=True))

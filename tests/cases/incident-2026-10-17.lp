% The morning of 2026-10-18: after a hibernate resume the ACPI battery is
% gone, the adapter method fails, UCSI still says 20 V x 5 A, and the EC
% (read directly) says on battery, discharging, 88 %.
sensor(acpi_bat;acpi_ac;ucsi;ec;trend).
trust(acpi_bat,2). trust(acpi_ac,2). trust(ucsi,1). trust(ec,5). trust(trend,3).
claim(acpi_bat,battery,absent).
claim(acpi_ac,ac,off).
claim(ucsi,ac,on).
claim(ec,ac,off). claim(ec,battery,present). claim(ec,flow,discharging).
reading(ec,pct,88).
claim(trend,flow,discharging). derived_from(trend,ec).
acpi_error(battery,"BAT1","_STA").
acpi_error(adapter,"ACAD","_PSR").
resumed(hibernate).

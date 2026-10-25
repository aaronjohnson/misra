% sky.lp: is it a grey day? The bar goes Solarized dark on one, even at noon.
%
% Observes only. The bar decides the theme: light = sun up and not gloomy.
%
% Input facts (collect/weather.py, from /run/misra-weather/now.json):
%   weather_age(S).    seconds since the weather was fetched
%   cloud(Pct).        cloud cover
%   rain(T).           precipitation, tenths of a millimetre, last 15 min
%   wmo(Code).         WMO weather code
%   radiation(W).      shortwave sunlight reaching the ground, W/m²
%   daylight. night.   the sun, as Open-Meteo sees it
%   was(gloomy).       last tick's verdict (the daemon's memory)

% Weather older than an hour says nothing.
fresh :- weather_age(A), A <= 3600.

wet  :- fresh, rain(R), R > 0.
wet  :- fresh, wmo(C), C >= 51, C <= 67.          % drizzle, rain, freezing rain
wet  :- fresh, wmo(C), C >= 80, C <= 82.          % rain showers
foggy :- fresh, wmo(C), C = 45.
foggy :- fresh, wmo(C), C = 48.
stormy :- fresh, wmo(C), C >= 95.
% Overcast alone isn't enough: a thin high layer still lights the room.
leaden :- fresh, daylight, cloud(C), C >= 90, radiation(W), W < 150.
bright :- fresh, radiation(W), W >= 300.

grey(rain)     :- wet.
grey(fog)      :- foggy.
grey(storm)    :- stormy.
grey(overcast) :- leaden.

% Hysteresis: once grey, stay grey while it's still mostly cloudy and not
% bright, so a passing gap in the clouds doesn't flip every screen for 15 min.
gloomy :- grey(_).
gloomy :- was(gloomy), fresh, cloud(C), C >= 75, not bright.
grey(lingering) :- gloomy, not grey(rain), not grey(fog), not grey(storm), not grey(overcast).

#show gloomy/0.
#show grey/1.

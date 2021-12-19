#!/usr/bin/env python3
import copy
import time
import random
import math
import argparse
from rpi_ws281x import PixelStrip

# LED strip configuration:
LED_COUNT = 100  # Number of LED pixels.
LED_PIN = 18  # GPIO pin connected to the pixels (18 uses PWM!).
LED_FREQ_HZ = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA = 10  # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 255  # Set to 0 for darkest and 255 for brightest
LED_INVERT = False  # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL = 0  # set to '1' for GPIOs 13, 19, 41, 45 or 53


class Color:
    def __init__(self, red=0, green=0, blue=0):
        self.red = red
        self.green = green
        self.blue = blue
        self.black = self.red == 0 and self.green == 0 and self.blue == 0

    def __iadd__(self, other):
        if other.black:
            return self
        if self.black is False:
            self.red += other.red
            self.green += other.green
            self.blue += other.blue
        else:
            self.black = False
            self.red = other.red
            self.green = other.green
            self.blue = other.blue
        return self

    def __imul__(self, other):
        if self.black:
            return self
        if other < 0:
            other = 0
        self.red *= other
        self.green *= other
        self.blue *= other
        return self

    def get(self):
        if self.black:
            return 0
        if self.red > 255:
            self.red = 255
        if self.green > 255:
            self.green = 255
        if self.blue > 255:
            self.blue = 255
        return (round(self.red) << 8) | (round(self.green) << 16) | round(self.blue)


def wheel(pos):
    """Generate rainbow colors across 0-255 positions."""
    if pos < 85:
        return Color(pos * 3, 255 - pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return Color(255 - pos * 3, 0, pos * 3)
    else:
        pos -= 170
        return Color(0, pos * 3, 255 - pos * 3)


def fixcolor(pos):
    if pos == 0:
        return Color(255, 0, 0)
    elif pos == 1:
        return Color(0, 255, 0)
    elif pos == 2:
        return Color(0, 0, 255)
    elif pos == 3:
        return Color(128, 128, 0)
    elif pos == 4:
        return Color(0, 128, 128)
    elif pos == 5:
        return Color(128, 0, 128)
    return Color(255, 255, 255)


class LightFunc:
    def __init__(self):
        self.state = 0

    def get(self, i) -> Color:
        return Color()

    def next_frame(self):
        self.state += 1


class LightFuncN:
    def __init__(self):
        self.state = [0] * LED_COUNT

    def get(self, i) -> Color:
        return Color()

    def next_frame(self):
        for i in range(LED_COUNT):
            if self.state[i]:
                self.state[i] -= 1


class FuncRainbow(LightFunc):
    def __init__(self):
        super().__init__()
        self.wave = random.randrange(2, 5) / 10
        self.pos = 0
        self.shift = random.randrange(20, 100) / 200

    def get(self, i) -> Color:
        c = wheel((self.state + i) & 255)
        c *= math.sin(i * self.wave + self.pos) * 0.4 + 0.6
        return c

    def next_frame(self):
        self.state += 1
        self.state &= 255
        self.pos += self.shift


class FuncMoveingDots1(LightFunc):
    def __init__(self, brighness=1.00, speed=1.00):
        super().__init__()
        self.brighness = brighness
        self.color = wheel(random.randrange(256))
        self.wave = random.randrange(2, 5) / 10
        self.shift = random.randrange(-100, 100) / 200 * speed

    def get(self, i) -> Color:
        m = math.sin(i * self.wave + self.state) * self.brighness
        if m < 0.1:
            c = Color()
        else:
            c = copy.copy(self.color)
            c *= m
        return c

    def next_frame(self):
        self.state += self.shift


class FuncMoveingDots2(LightFunc):
    def __init__(self):
        super().__init__()
        self.color = wheel(random.randrange(256))
        self.wave = 2 * math.pi * (random.randrange(3) + 1) / LED_COUNT
        self.speed = random.randrange(-100, 100) / 200

    def get(self, i) -> Color:
        m = math.sin(i * self.wave + self.state) * 4 - 3
        if m < 0.1:
            c = Color()
        else:
            c = copy.copy(self.color)
            c *= m
        return c

    def next_frame(self):
        self.state += self.speed


class FuncMoveCombine(LightFunc):
    def __init__(self):
        super().__init__()
        self.f1 = FuncMoveingDots1(0.2, 0.1)
        self.f2 = FuncMoveingDots2()

    def get(self, i) -> Color:
        c = self.f1.get(i)
        c += self.f2.get(i)
        return c

    def next_frame(self):
        self.f1.next_frame()
        self.f2.next_frame()


class FuncFade1(LightFuncN):
    def __init__(self):
        super().__init__()
        self.color = wheel(random.randrange(256))

    def get(self, i) -> Color:
        s = self.state[i]
        if s == 0:
            return Color()
        ret = copy.copy(self.color)
        if s < 20:
            ret *= s / 20
        else:
            ret *= (25 - s) / 5
        return ret

    def next_frame(self):
        super().next_frame()
        if random.randrange(5) == 0:
            i = random.randrange(LED_COUNT)
            if self.state[i] == 0:
                self.state[i] = 24


class FuncFade2(LightFuncN):
    def __init__(self):
        super().__init__()
        self.fast = 20
        self.slow = 50
        self.slow2 = self.slow * 2
        self.color1 = wheel(random.randrange(256))
        self.color2 = fixcolor(random.randrange(7))
        self.color2 *= 0.08
        for i in range(LED_COUNT):
            self.state[i] = random.randrange(self.slow * 2)

    def get(self, i) -> Color:
        s = self.state[i]
        ret = copy.copy(self.color2)
        if s <= self.slow2:
            if s < self.slow:
                ret *= (self.slow - s) / self.slow
            else:
                ret *= (s - self.slow) / self.slow
            return ret
        chigh = copy.copy(self.color1)
        if s < self.slow2 + self.fast:
            chigh *= (s - self.slow2) / self.fast
            ret += chigh
        else:
            chigh *= (self.slow2 + self.fast + 5 - s) / 5
            return chigh
        return ret

    def next_frame(self):
        for i in range(LED_COUNT):
            if self.state[i]:
                self.state[i] -= 1
            else:
                self.state[i] = self.slow2
        if random.randrange(10) == 0:
            i = random.randrange(LED_COUNT)
            if self.state[i] <= self.slow2:
                self.state[i] = self.slow2 + self.fast + 4


class FuncSparkling1(LightFuncN):
    def __init__(self):
        super().__init__()
        self.slow = 50
        self.slow2 = self.slow * 2
        self.color1 = wheel(random.randrange(256))
        self.color2 = fixcolor(random.randrange(7))
        self.color2 *= 0.08
        for i in range(LED_COUNT):
            self.state[i] = random.randrange(self.slow * 2)

    def get(self, i) -> Color:
        s = self.state[i]
        if random.randrange(LED_COUNT * 10) == 0:
            ret = copy.copy(self.color1)
        else:
            ret = copy.copy(self.color2)
            if s <= self.slow2:
                if s < self.slow:
                    ret *= (self.slow - s) / self.slow
                else:
                    ret *= (s - self.slow) / self.slow
        return ret

    def next_frame(self):
        for i in range(LED_COUNT):
            if self.state[i]:
                self.state[i] -= 1
            else:
                self.state[i] = self.slow2


class Tree:
    def __init__(self, arguments):
        self.args = arguments
        self.strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
        self.strip.begin()
        self.func1 = None  # typing.Optional[LightFunc, LightFuncN]
        self.func2 = None  # typing.Optional[LightFunc, LightFuncN]
        self.mix = 0
        self.funclist = [FuncRainbow, FuncMoveingDots1, FuncMoveingDots2, FuncMoveCombine, FuncFade1, FuncFade2,
                         FuncSparkling1]
        self.fixfunc = None
        if self.args.action is not None and self.args.action < len(self.funclist):
            self.fixfunc = self.funclist[self.args.action]
        if self.args.wait < 0:
            self.args.wait = 0
        random.seed()

    def _random_func(self):
        choice = self.fixfunc if self.fixfunc is not None else random.choice(self.funclist)
        if self.args.v:
            print(f"Next scene: {choice.__name__}")
        return choice()

    def run(self):
        self.func1 = self._random_func()
        t = time.time()
        t_next_scene = t + self.args.wait
        t_next = t + 0.04
        t_fps = t
        fps = 0
        try:
            while True:
                for i in range(LED_COUNT):
                    c = self.func1.get(i)
                    if self.func2 is not None:
                        c *= (1 - self.mix)
                        c2 = self.func2.get(i)
                        c2 *= self.mix
                        c += c2
                    try:
                        self.strip.setPixelColor(i, c.get())
                    except OverflowError:
                        print(c)
                        print(c.get())
                self.strip.show()
                self.func1.next_frame()
                t = time.time()
                if self.func2 is None:
                    if t_next_scene < t:
                        self.func2 = self._random_func()
                        self.mix = 0
                else:
                    self.mix += 0.02
                    if self.mix >= 1:
                        self.func1 = self.func2
                        self.func2 = None
                        t_next_scene = t + self.args.wait
                    else:
                        self.func2.next_frame()
                if self.args.fps:
                    fps += 1
                    if t_fps + 1 <= t:
                        t_fps += 1
                        print(f"FPS: {fps}")
                        fps = 0
                t = time.time()
                w = t_next - t
                if w >= 0.01:
                    t_next += 0.04
                else:
                    w = 0.01
                    t_next = t + 0.05
                time.sleep(w)
        except KeyboardInterrupt:
            pass
        if self.args.clear:
            for i in range(LED_COUNT):
                self.strip.setPixelColor(i, 0)
            self.strip.show()


if __name__ == '__main__':
    print('Press Ctrl-C to quit.')
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--action", type=int, help="selected action", default=None)
    parser.add_argument("-w", "--wait", type=int, help="wait per screen", default=20)
    parser.add_argument('-c', '--clear', action='store_true', help='clear the display on exit')
    parser.add_argument('-f', '--fps', action='store_true', help='display FPS')
    parser.add_argument('-v', action='store_true', help='Verbose')
    args = parser.parse_args()
    tree = Tree(args)
    tree.run()

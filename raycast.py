import os
import sys
import math
import random
import itertools

import sdl # pysdl2-cffi

from collections import namedtuple

if sys.version_info[0] == 2:
    range = xrange

CAPTION = "Raytracing with Python"
SCREEN_SIZE = (1200, 600)
CIRCLE = 2*math.pi
SCALE = (SCREEN_SIZE[0]+SCREEN_SIZE[1])/1200.0
FIELD_OF_VIEW = math.pi*0.4
NO_WALL = float("inf")
RAIN_COLOR = (255, 255, 255, 40)


# Semantically meaningful tuples for use in GameMap and Camera class.
RayInfo = namedtuple("RayInfo", ["sin", "cos"])
WallInfo = namedtuple("WallInfo", ["top", "height"])


class Image(object):
    """A very basic class that couples an image with its dimensions"""
    def __init__(self, image):
        """
        The image argument is a preloaded and converted pg.Surface object.
        """
        self.image = image
        self.width, self.height = sdl.queryTexture(image)[-2:]


class Player(object):
    """Handles the player's position, rotation, and control."""
    def __init__(self, x, y, direction):
        """
        The arguments x and y are floating points.  Anything between zero
        and the game map size is on our generated map.
        Choosing a point outside this range ensures our player doesn't spawn
        inside a wall.  The direction argument is the initial angle (given in
        radians) of the player.
        """
        self.x = x
        self.y = y
        self.direction = direction
        self.speed = 3 # Map cells per second.
        self.rotate_speed = CIRCLE/2  # 180 degrees in a second.
        self.weapon = Image(IMAGES["knife"])
        self.paces = 0 # Used for weapon placement.

    def rotate(self, angle):
        """Change the player's direction when appropriate key is pressed."""
        self.direction = (self.direction+angle+CIRCLE)%CIRCLE

    def walk(self, distance, game_map):
        """
        Calculate the player's next position, and move if he will
        not end up inside a wall.
        """
        dx = math.cos(self.direction)*distance
        dy = math.sin(self.direction)*distance
        if game_map.get(self.x+dx, self.y) <= 0:
            self.x += dx
        if game_map.get(self.x, self.y+dy) <= 0:
            self.y += dy
        self.paces += distance

    def update(self, keys, dt, game_map):
        """Execute movement functions if the appropriate key is pressed."""
        if keys[sdl.SCANCODE_LEFT]:
            self.rotate(-self.rotate_speed*dt)
        if keys[sdl.SCANCODE_RIGHT]:
            self.rotate(self.rotate_speed*dt)
        if keys[sdl.SCANCODE_UP]:
            self.walk(self.speed*dt, game_map)
        if keys[sdl.SCANCODE_DOWN]:
            self.walk(-self.speed*dt, game_map)


class GameMap(object):
    """
    A class to generate a random map for us; handle ray casting;
    and provide a method of detecting colissions.
    """
    def __init__(self, size):
        """
        The size argument is an integer which tells us the width and height
        of our game grid.  For example, a size of 32 will create a 32x32 map.
        """
        self.size = size
        self.wall_grid = self.randomize()
        self.sky_box = Image(IMAGES["sky"])
        self.wall_texture = Image(IMAGES["texture"])
        self.light = 0

    def get(self, x, y):
        """A method to check if a given coordinate is colliding with a wall."""
        point = (int(math.floor(x)), int(math.floor(y)))
        return self.wall_grid.get(point, -1)

    def randomize(self):
        """
        Generate our map randomly.  In the code below their is a 30% chance
        of a cell containing a wall.
        """
        coordinates = itertools.product(range(self.size), repeat=2)
        return {coord : random.random()<0.3 for coord in coordinates}

    def cast_ray(self, point, angle, cast_range):
        """
        The meat of our ray casting program.  Given a point,
        an angle (in radians), and a maximum cast range, check if any
        collisions with the ray occur.  Casting will stop if a collision is
        detected (cell with greater than 0 height), or our maximum casting
        range is exceeded without detecting anything.
        """
        info = RayInfo(math.sin(angle), math.cos(angle))
        origin = Point(point)
        ray = [origin]
        while origin.height <= 0 and origin.distance <= cast_range:
            dist = origin.distance
            step_x = origin.step(info.sin, info.cos)
            step_y = origin.step(info.cos, info.sin, invert=True)
            if step_x.length < step_y.length:
                next_step = step_x.inspect(info, self, 1, 0, dist, step_x.y)
            else:
                next_step = step_y.inspect(info, self, 0, 1, dist, step_y.x)
            ray.append(next_step)
            origin = next_step
        return ray

    def update(self, dt):
        """Adjust ambient lighting based on time."""
        if self.light > 0:
            self.light = max(self.light-10*dt, 0)
        elif random.random()*5 < dt:
            self.light = 2


class Point(object):
    """
    A fairly basic class to assist us with ray casting.  The return value of
    the GameMap.cast_ray() method is a list of Point instances.
    """
    def __init__(self, point, length=None):
        self.x = point[0]
        self.y = point[1]
        self.height = 0
        self.distance = 0
        self.shading = None
        self.length = length

    def step(self, rise, run, invert=False):
        """
        Return a new Point advanced one step from the caller.  If run is
        zero, the length of the new Point will be infinite.
        """
        try:
            x, y = (self.y,self.x) if invert else (self.x,self.y)
            dx = math.floor(x+1)-x if run > 0 else math.ceil(x-1)-x
            dy = dx*(rise/run)
            next_x = y+dy if invert else x+dx
            next_y = x+dx if invert else y+dy
            length = math.hypot(dx, dy)
        except ZeroDivisionError:
            next_x = next_y = None
            length = NO_WALL
        return Point((next_x,next_y), length)

    def inspect(self, info, game_map, shift_x, shift_y, distance, offset):
        """
        Ran when the step is selected as the next in the ray.
        Sets the steps self.height, self.distance, and self.shading,
        to the required values.
        """
        dx = shift_x if info.cos<0 else 0
        dy = shift_y if info.sin<0 else 0
        self.height = game_map.get(self.x-dx, self.y-dy)
        self.distance = distance+self.length
        if shift_x:
            self.shading = 2 if info.cos<0 else 0
        else:
            self.shading = 2 if info.sin<0 else 1
        self.offset = offset-math.floor(offset)
        return self


class Camera(object):
    """Handles the projection and rendering of all objects on the screen."""
    def __init__(self, screen, resolution):
        self.screen = screen
        self.width, self.height = self.screen.getWindowSize()
        self.resolution = float(resolution)
        self.spacing = self.width/resolution
        self.field_of_view = FIELD_OF_VIEW
        self.range = 8
        self.light_range = 5
        self.scale = SCALE

    def render(self, player, game_map):
        """Render everything in order."""
        self.draw_sky(player.direction, game_map.sky_box)
        self.draw_columns(player, game_map)
        self.draw_weapon(player.weapon, player.paces)

    def draw_sky(self, direction, sky):
        """Calculate the skies offset so that it wraps, and draw."""
        left = -sky.width*direction/CIRCLE
        renderer.renderCopy(sky.image, 
                sdl.ffi.NULL,
                (int(left), 0, 
                 sky.width, sky.height))
        if left<sky.width-self.width:
            renderer.renderCopy(sky.image, 
                    sdl.ffi.NULL,
                    (int(left)+sky.width, 0, 
                     sky.width, sky.height))

    def draw_columns(self, player, game_map):
        """
        For every column in the given resolution, cast a ray, and render that
        column.
        """
        for column in range(int(self.resolution)):
            angle = self.field_of_view*(column/self.resolution-0.5)
            point = player.x, player.y
            ray = game_map.cast_ray(point, player.direction+angle, self.range)
            self.draw_column(column, ray, angle, game_map)

    def draw_column(self, column, ray, angle, game_map):
        """
        Check if a hit occurs in the ray.  Then itterate through each step
        of the ray (in reverse).  A hit will be rendered
        (including its shadow).  Rain drops will be drawn for each step.
        """
        texture = game_map.wall_texture
        left = int(math.floor(column*self.spacing))
        width = int(math.ceil(self.spacing))
        hit = 0
        while hit < len(ray) and ray[hit].height <= 0:
            hit += 1
        for ray_index in range(len(ray)-1, -1, -1):
            step = ray[ray_index]
            if ray_index == hit:
                texture_x = int(math.floor(texture.width*step.offset))
                wall = self.project(step.height, angle, step.distance)
                image_location = sdl.Rect((texture_x, 0, 1, texture.height))
                scale_rect = sdl.Rect(tuple(int(x) for x in (left, wall.top, width, wall.height)))
                renderer.renderCopy(texture.image, image_location, scale_rect)
                self.draw_shadow(step, scale_rect, game_map.light)
            self.draw_rain(step, angle, left, ray_index)

    def draw_shadow(self, step, scale_rect, light):
        """
        Render the shadow on a column with regards to its distance and
        shading attribute.
        """
        shade_value = step.distance+step.shading
        max_light = shade_value/float(self.light_range-light)
        alpha = 255*min(1, max(max_light, 0))

        renderer.setRenderDrawColor(0,0,0,int(alpha))
        renderer.setRenderDrawBlendMode(sdl.BLENDMODE_BLEND)
        renderer.renderFillRect(scale_rect)

    def draw_rain(self, step, angle, left, ray_index):
        """
        Render a number of rain drops to add depth to our scene and mask
        roughness.
        """
        rain_drops = int(random.random()**3*ray_index)
        if rain_drops:
            rain = self.project(0.1, angle, step.distance)
        renderer.setRenderDrawColor(*RAIN_COLOR)
        renderer.setRenderDrawBlendMode(sdl.BLENDMODE_BLEND)
        for _ in range(rain_drops):
            rain_top = int(random.random() * rain.top)
            renderer.renderDrawLine(int(left), rain_top,
                                    int(left), int(rain_top + rain.height))

    def draw_weapon(self, weapon, paces):
        """
        Calulate new weapon position based on player's pace attribute,
        and render.
        """
        bob_x = math.cos(paces*2)*self.scale*6
        bob_y = math.sin(paces*4)*self.scale*6
        left = self.width*0.66+bob_x
        top = self.height*0.6+bob_y
        renderer.renderCopy(weapon.image,
                            sdl.ffi.NULL,
                            (int(left), int(top), weapon.width, weapon.height))

    def project(self, height, angle, distance):
        """
        Find the position on the screen after perspective projection.
        A minimum value is used for z to prevent slices blowing up to
        unmanageable sizes when the player is very close.
        """
        z = max(distance*math.cos(angle),0.2)
        wall_height = self.height*height/float(z)
        bottom = self.height/float(2)*(1+1/float(z))
        return WallInfo(bottom-wall_height, int(wall_height))


class Control(object):
    """
    The core of our program.  Responsible for running our main loop;
    processing events; updating; and rendering.
    """
    def __init__(self):
        # self.screen = pg.display.get_surface()
        self.fps = 60.0
        self.done = False
        self.player = Player(15.3, -1.2, math.pi*0.3)
        self.game_map = GameMap(32)
        self.camera = Camera(window, 300)
        self.keys = None

    def event_loop(self):
        """
        Quit game on a quit event and update self.keys on any keyup or keydown.
        """
        event = sdl.Event()
        while event.pollEvent():
            if event.type == sdl.QUIT:
                self.done = True

    def update(self, dt):
        """Update the game_map and player."""
        self.game_map.update(dt)
        keys = sdl.getKeyboardState()[0] # (keystate, length)
        self.player.update(keys, dt, self.game_map)

    def display_fps(self, fps):
        """Show the program's FPS in the window handle."""
        caption = "{} - FPS: {:.2f}".format(CAPTION, fps)
        window.setWindowTitle(caption.encode('utf-8'))

    def main_loop(self):
        """Process events, update, and render."""
        dt = sdl.getTicks() / 1000.
        fps = 0
        fps_reported = 0
        while not self.done:
            self.event_loop()
            self.update(dt)
            self.camera.render(self.player, self.game_map)
            ticks = sdl.getTicks()
            dt = (ticks / 1000.) - dt
            renderer.renderPresent()
            renderer.setRenderDrawColor(0,0,0,255)
            renderer.renderClear()
            fps += 1
            if ticks - fps_reported > 1000: # report once a second
                self.display_fps(fps)
                fps = 0
                fps_reported = ticks

def load_resources():
    """
    Return a dictionary of our needed images; loaded, converted, and scaled.
    """
    images = {}

    knife_image = sdl.image.load("knife_hand.png")
    try:
        knife_w, knife_h = knife_image.w, knife_image.h
        knife_scale = (int(knife_w*SCALE), int(knife_h*SCALE))
        images["knife"] = renderer.createTextureFromSurface(knife_image)
    finally:
        sdl.freeSurface(knife_image)
    images["texture"] = sdl.image.loadTexture(renderer, 'wall_texture.jpg')
    sky_size = int(SCREEN_SIZE[0]*(CIRCLE/FIELD_OF_VIEW)), SCREEN_SIZE[1]
    sky_box_image = sdl.image.loadTexture(renderer, "deathvalley_panorama.jpg")
    images["sky"] = sky_box_image

    return images


def main():
    """Prepare the display, load images, and get our programming running."""
    global IMAGES, window, renderer
    os.environ["SDL_VIDEO_CENTERED"] = "True"
    sdl.init(sdl.INIT_VIDEO)
    try:
        window = sdl.createWindow(CAPTION.encode('utf-8'),
                                  sdl.WINDOWPOS_CENTERED,
                                  sdl.WINDOWPOS_CENTERED,
                                  SCREEN_SIZE[0],
                                  SCREEN_SIZE[1],
                                  0)
        window = sdl.Window(window)
        renderer = sdl.Renderer(sdl.createRenderer(window, -1, 0))
        IMAGES = load_resources()
        Control().main_loop()
    finally:
        sdl.quit()

if __name__ == "__main__":
    main()

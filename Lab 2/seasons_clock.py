import time
import digitalio
import board
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789

# --- Display and Pin Configuration (unchanged from your original code) ---
cs_pin = digitalio.DigitalInOut(board.D5)
dc_pin = digitalio.DigitalInOut(board.D25)
reset_pin = None
BAUDRATE = 64000000
spi = board.SPI()
disp = st7789.ST7789(
    spi,
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=BAUDRATE,
    width=135,
    height=240,
    x_offset=53,
    y_offset=40,
)

# --- Image Setup ---
# Get display dimensions
height = disp.width
width = disp.height
rotation = 90

# Pre-load all the season images
# Make sure your image files are named and located correctly
seasons = ['fall.png', 'winter.png', 'spring.png', 'summer.png']
images = []
for season in seasons:
    img_path = f'images/seasons/{season}'
    img = Image.open(img_path).convert('RGB')
    
    # Resize the image to fit the display while maintaining aspect ratio
    img.thumbnail((width, height), Image.Resampling.LANCZOS)
    
    # Create a new blank image and paste the resized image onto it to center it
    new_img = Image.new("RGB", (width, height), (0, 0, 0))
    paste_x = (width - img.width) // 2
    paste_y = (height - img.height) // 2
    new_img.paste(img, (paste_x, paste_y))
    
    images.append(new_img)

# --- Backlight and Clock/Date Setup ---
backlight = digitalio.DigitalInOut(board.D22)
backlight.switch_to_output()
backlight.value = True

font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)

# --- Main Loop with Image and Season Counter Display ---
image_index = 0
last_image_change_time = time.time()
image_change_interval = 10  # seconds

# Initialize a counter for the seasons
seasons_passed = 0

while True:
    current_time = time.time()

    # Check if it's time to switch the image
    if current_time - last_image_change_time >= image_change_interval:
        image_index = (image_index + 1) % len(images)  # Cycle to the next image
        last_image_change_time = current_time  # Reset the timer
        
        # Increment the seasons counter each time the image changes
        seasons_passed += 1

    # Get the current image to display
    current_image = images[image_index]

    # Create a copy of the current image to draw the text on
    display_image = current_image.copy()
    draw = ImageDraw.Draw(display_image)

    # Create the text string with the seasons counter
    seasons_text = f"Seasons: {seasons_passed}"

    # Use textbbox() to get the bounding box of the text
    bbox = draw.textbbox((0, 0), seasons_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Calculate centered position at the bottom of the screen
    text_x = (width - text_width) // 2
    text_y = height - text_height - 5

    # Draw the text on the image copy
    draw.text((text_x, text_y), seasons_text, font=font, fill="#FFFFFF")

    # Display the final image on the screen
    disp.image(display_image, rotation)

    # Sleep to prevent the loop from running too fast
    time.sleep(0.1)
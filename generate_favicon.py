from PIL import Image, ImageDraw, ImageColor

# Create a 16x16 favicon
size = 16
image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)

# Draw a simple play button
# Red circle
draw.ellipse([(2, 2), (14, 14)], fill=(255, 0, 0, 255))
# White play triangle
triangle = [(5, 4), (5, 12), (11, 8)]
draw.polygon(triangle, fill=(255, 255, 255, 255))

image.save('static/favicon.ico', format='ICO')
print("Favicon created successfully at static/favicon.ico")

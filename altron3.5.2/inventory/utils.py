import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError

def generate_barcode(sequence_number):
    try:
        code128 = barcode.get_barcode_class('code128')
        barcode_instance = code128(sequence_number, writer=ImageWriter())

        buffer = BytesIO()
        barcode_instance.write(buffer, options={"write_text": True})

        filename = f"{sequence_number}.png"
        return ContentFile(buffer.getvalue(), name=filename)
    except Exception as e:
        raise ValidationError(f"Failed to generate barcode for {sequence_number}: {e}")

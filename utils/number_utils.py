from num2words import num2words
import logging
def number_to_words_bangladesh(number):
    """Convert number to Bangladeshi Bengali format words"""
    # Handle zero as a special case
    if number == 0:
        return "zero"

    # Handle negative numbers
    if number < 0:
        return f"negative {number_to_words_bangladesh(abs(number))}"

    # Try using the num2words library with Bengali
    try:
        return num2words(number, lang='bn')
    except NotImplementedError:
        # Fallback if Bengali language not available
        logging.getLogger(__name__).warning("Bengali language not available in num2words, using fallback")
    except Exception as e:
        # Log or handle other exceptions
        logging.getLogger(__name__).warning("Bengali language not available in num2words, using fallback")

    # Handle decimal part
    int_part = int(number)
    decimal_part = number - int_part

    # Convert the integer part
    def convert_below_crore(n):
        if n >= 100000:  # 1 lakh and above
            lakhs = n // 100000
            remainder = n % 100000
            if remainder == 0:
                return f"{int(lakhs)} lakh"
            elif remainder >= 1000:
                thousands = remainder // 1000
                final_remainder = remainder % 1000
                if final_remainder == 0:
                    return f"{int(lakhs)} lakh {int(thousands)} thousand"
                else:
                    return f"{int(lakhs)} lakh {int(thousands)} thousand {int(final_remainder)}"
            else:
                return f"{int(lakhs)} lakh {int(remainder)}"
        elif n >= 1000:
            thousands = n // 1000
            remainder = n % 1000
            if remainder == 0:
                return f"{int(thousands)} thousand"
            else:
                return f"{int(thousands)} thousand {int(remainder)}"
        else:
            return str(int(n))

    # Main conversion logic
    result = ""
    if int_part >= 10000000:  # 1 crore and above
        crores = int_part // 10000000
        remainder = int_part % 10000000
        if remainder == 0:
            result = f"{int(crores)} crore"
        else:
            remainder_words = convert_below_crore(remainder)
            result = f"{int(crores)} crore {remainder_words}"
    else:
        result = convert_below_crore(int_part)

    # Add decimal part if present
    if decimal_part > 0:
        decimal_str = str(decimal_part).split('.')[1]
        result += f" point {' '.join(decimal_str)}"

    return result
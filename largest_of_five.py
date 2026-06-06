def get_number(prompt):
    """Prompts the user for a number and handles invalid non-numeric inputs."""
    while True:
        try:
            return float(input(prompt))
        except ValueError:
            print("Invalid input. Please enter a valid numerical value.")

def main():
    print("--- Find the Largest and Smallest of 5 Numbers ---")
    numbers = []
    for i in range(1, 6):
        num = get_number(f"Enter number {i}: ")
        numbers.append(num)
    
    largest = max(numbers)
    smallest = min(numbers)
    
    print("\nResults:")
    print(f"Numbers entered: {numbers}")
    print(f"The largest number is: {largest}")
    print(f"The smallest number is: {smallest}")

if __name__ == "__main__":
    main()

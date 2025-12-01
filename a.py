from app.routes import evaluate_code_with_custom_system

code = """
public class Program
{
    public static long factorial(int n)
    {
        if (n == 0)
            return 1;

        long result = 1;
        for (int i = 1; i <= n; i++)
        {
            result *= i;
        }
        return result;
    }

    // Optional Main() for running manually
    public static void Main()
    {
        // Unit tests
        System.Diagnostics.Debug.Assert(factorial(5) == 120);
        System.Diagnostics.Debug.Assert(factorial(0) == 1);
        System.Diagnostics.Debug.Assert(factorial(7) == 5040);

        System.Console.WriteLine("All tests passed.");
    }
}

"""

tests = """assert factorial(5) == 120;
assert factorial(0) == 1;
assert factorial(7) == 5040;"""

print(evaluate_code_with_custom_system(code, "Compute factorial in C#", tests))

#!/usr/bin/env python3
"""
API Stress Testing Script
Phase 6 Sprint 5: Production Deployment & Testing

Stress tests for API endpoints with concurrent requests and response time validation.
"""

import asyncio
import aiohttp
import time
import statistics
from typing import List, Dict, Any
from dataclasses import dataclass, field
import sys


@dataclass
class TestResult:
    """Test result data"""
    endpoint: str
    method: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    response_times: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def avg_response_time(self) -> float:
        """Average response time in ms"""
        if not self.response_times:
            return 0.0
        return statistics.mean(self.response_times)

    @property
    def p95_response_time(self) -> float:
        """95th percentile response time in ms"""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        index = int(len(sorted_times) * 0.95)
        return sorted_times[index]

    @property
    def p99_response_time(self) -> float:
        """99th percentile response time in ms"""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        index = int(len(sorted_times) * 0.99)
        return sorted_times[index]


class StressTestRunner:
    """Stress test runner for API endpoints"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = None

    async def __aenter__(self):
        """Setup async session"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup async session"""
        if self.session:
            await self.session.close()

    async def make_request(self, method: str, endpoint: str, **kwargs) -> tuple[bool, float, str]:
        """
        Make a single request and measure response time.

        Returns:
            (success, response_time_ms, error_message)
        """
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()

        try:
            async with self.session.request(method, url, **kwargs) as response:
                response_time = (time.time() - start_time) * 1000
                await response.read()  # Consume response body

                success = 200 <= response.status < 400
                error = "" if success else f"HTTP {response.status}"

                return success, response_time, error

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return False, response_time, str(e)

    async def stress_test_endpoint(
        self,
        endpoint: str,
        method: str = "GET",
        concurrent_requests: int = 100,
        total_requests: int = 1000,
        **request_kwargs
    ) -> TestResult:
        """
        Stress test a single endpoint with concurrent requests.

        Args:
            endpoint: API endpoint path
            method: HTTP method
            concurrent_requests: Number of concurrent requests
            total_requests: Total number of requests to make
            **request_kwargs: Additional request parameters (json, data, headers, etc.)
        """
        result = TestResult(
            endpoint=endpoint,
            method=method,
            total_requests=total_requests,
            successful_requests=0,
            failed_requests=0
        )

        # Create batches of concurrent requests
        batch_size = concurrent_requests
        batches = [
            range(i, min(i + batch_size, total_requests))
            for i in range(0, total_requests, batch_size)
        ]

        print(f"\nStress testing {method} {endpoint}")
        print(f"  Total requests: {total_requests}")
        print(f"  Concurrent requests: {concurrent_requests}")
        print(f"  Batches: {len(batches)}")

        for batch_num, batch in enumerate(batches, 1):
            # Create concurrent tasks for this batch
            tasks = [
                self.make_request(method, endpoint, **request_kwargs)
                for _ in batch
            ]

            # Execute batch concurrently
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for task_result in batch_results:
                if isinstance(task_result, Exception):
                    result.failed_requests += 1
                    result.errors.append(str(task_result))
                else:
                    success, response_time, error = task_result
                    result.response_times.append(response_time)

                    if success:
                        result.successful_requests += 1
                    else:
                        result.failed_requests += 1
                        if error:
                            result.errors.append(error)

            # Progress indicator
            completed = batch_num * batch_size
            progress = min(completed, total_requests)
            print(f"  Progress: {progress}/{total_requests} requests completed")

        return result

    def print_results(self, result: TestResult):
        """Print formatted test results"""
        print(f"\n{'='*80}")
        print(f"Results for {result.method} {result.endpoint}")
        print(f"{'='*80}")
        print(f"Total Requests:      {result.total_requests}")
        print(f"Successful:          {result.successful_requests} ({result.success_rate:.2f}%)")
        print(f"Failed:              {result.failed_requests}")
        print(f"\nResponse Times (ms):")
        print(f"  Average:           {result.avg_response_time:.2f}")
        print(f"  P95:               {result.p95_response_time:.2f}")
        print(f"  P99:               {result.p99_response_time:.2f}")
        print(f"  Min:               {min(result.response_times):.2f}" if result.response_times else "  Min:               N/A")
        print(f"  Max:               {max(result.response_times):.2f}" if result.response_times else "  Max:               N/A")

        # Show validation against targets
        print(f"\n{'Target Validation':^80}")
        print(f"{'-'*80}")

        # Target: <2s average response time
        avg_target = 2000  # 2 seconds in ms
        avg_pass = result.avg_response_time < avg_target
        print(f"  Avg Response Time:  {result.avg_response_time:.2f}ms < {avg_target}ms  {'✅ PASS' if avg_pass else '❌ FAIL'}")

        # Target: <5% error rate
        error_rate = (result.failed_requests / result.total_requests) * 100
        error_target = 5.0
        error_pass = error_rate < error_target
        print(f"  Error Rate:         {error_rate:.2f}% < {error_target}%  {'✅ PASS' if error_pass else '❌ FAIL'}")

        if result.errors:
            print(f"\nError Summary:")
            unique_errors = list(set(result.errors[:10]))  # Show up to 10 unique errors
            for error in unique_errors:
                count = result.errors.count(error)
                print(f"  - {error} (x{count})")

        print(f"{'='*80}\n")


async def run_stress_tests():
    """Run all stress tests"""
    async with StressTestRunner() as runner:
        results = []

        # Test 1: Health endpoint (should be very fast)
        result = await runner.stress_test_endpoint(
            endpoint="/api/v1/health/live",
            method="GET",
            concurrent_requests=50,
            total_requests=500
        )
        results.append(result)
        runner.print_results(result)

        # Test 2: Template listing (moderate complexity)
        result = await runner.stress_test_endpoint(
            endpoint="/api/v1/templates?page=1&page_size=20",
            method="GET",
            concurrent_requests=50,
            total_requests=500
        )
        results.append(result)
        runner.print_results(result)

        # Test 3: Featured templates (database query)
        result = await runner.stress_test_endpoint(
            endpoint="/api/v1/templates/featured?limit=10",
            method="GET",
            concurrent_requests=50,
            total_requests=500
        )
        results.append(result)
        runner.print_results(result)

        # Test 4: Template search (complex query)
        result = await runner.stress_test_endpoint(
            endpoint="/api/v1/templates?query=retail&category=distribution&page=1",
            method="GET",
            concurrent_requests=30,
            total_requests=300
        )
        results.append(result)
        runner.print_results(result)

        # Test 5: Metrics endpoint
        result = await runner.stress_test_endpoint(
            endpoint="/api/v1/metrics/json",
            method="GET",
            concurrent_requests=50,
            total_requests=500
        )
        results.append(result)
        runner.print_results(result)

        # Overall summary
        print(f"\n{'='*80}")
        print(f"{'OVERALL SUMMARY':^80}")
        print(f"{'='*80}")

        total_requests = sum(r.total_requests for r in results)
        total_successful = sum(r.successful_requests for r in results)
        total_failed = sum(r.failed_requests for r in results)
        overall_success_rate = (total_successful / total_requests) * 100

        all_response_times = []
        for r in results:
            all_response_times.extend(r.response_times)

        print(f"Total Tests:         {len(results)}")
        print(f"Total Requests:      {total_requests}")
        print(f"Successful:          {total_successful} ({overall_success_rate:.2f}%)")
        print(f"Failed:              {total_failed}")
        print(f"\nOverall Response Times (ms):")
        print(f"  Average:           {statistics.mean(all_response_times):.2f}")
        print(f"  Median:            {statistics.median(all_response_times):.2f}")
        print(f"  P95:               {sorted(all_response_times)[int(len(all_response_times) * 0.95)]:.2f}")
        print(f"  P99:               {sorted(all_response_times)[int(len(all_response_times) * 0.99)]:.2f}")

        # Overall validation
        overall_avg = statistics.mean(all_response_times)
        overall_error_rate = (total_failed / total_requests) * 100

        print(f"\n{'Overall Validation':^80}")
        print(f"{'-'*80}")
        avg_pass = overall_avg < 2000
        error_pass = overall_error_rate < 5.0

        print(f"  Avg Response Time:  {overall_avg:.2f}ms < 2000ms  {'✅ PASS' if avg_pass else '❌ FAIL'}")
        print(f"  Error Rate:         {overall_error_rate:.2f}% < 5%  {'✅ PASS' if error_pass else '❌ FAIL'}")

        if avg_pass and error_pass:
            print(f"\n{'✅ ALL TESTS PASSED':^80}")
        else:
            print(f"\n{'❌ SOME TESTS FAILED':^80}")

        print(f"{'='*80}\n")

        return avg_pass and error_pass


if __name__ == "__main__":
    print("API Stress Testing Suite")
    print("="*80)
    print("Starting stress tests...")
    print("Please ensure the backend is running at http://localhost:8000")
    print("="*80)

    success = asyncio.run(run_stress_tests())
    sys.exit(0 if success else 1)

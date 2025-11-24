# import urllib.request
# import urllib.error
# import concurrent.futures
# import time
# import sys
# def make_request(request_id):
#     url = "http://localhost:8000/api/users/888"
#     start_time = time.time()
#     try:
#         req = urllib.request.Request(url, method='GET')
#         with urllib.request.urlopen(req, timeout=10) as response:
#             end_time = time.time()
#             response_time = end_time - start_time
#             status_code = response.getcode()
#             return {
#                 'id': request_id,
#                 'status': status_code,
#                 'time': response_time,
#                 'success': status_code == 200
#             }
#     except urllib.error.HTTPError as e:
#         end_time = time.time()
#         return {
#             'id': request_id,
#             'status': e.code,
#             'time': end_time - start_time,
#             'success': False,
#             'error': str(e)
#         }
#     except Exception as e:
#         end_time = time.time()
#         return {
#             'id': request_id,
#             'status': 'Error',
#             'time': end_time - start_time,
#             'success': False,
#             'error': str(e)
#         }

# def main():
#     print("Starting load test: 300 requests")
    
#     start_time = time.time()
    
#     # Use ThreadPoolExecutor for concurrent requests
#     with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
#         # Submit 300 requests
#         futures = [executor.submit(make_request, i) for i in range(100)]
        
#         results = []
#         for future in concurrent.futures.as_completed(futures):
#             results.append(future.result())
    
#     total_time = time.time() - start_time
#     successful = sum(1 for r in results if r['success'])
#     average_time = sum(r['time'] for r in results) / len(results)
#     requests_per_sec = 300 / total_time
    
#     print("\n=== RESULTS ===")
#     print(f"Total requests: 300")
#     print(f"Successful: {successful}")
#     print(f"Failed: {300 - successful}")
#     print(f"Total time: {total_time:.2f} seconds")
#     print(f"Average response time: {average_time:.3f} seconds")
#     print(f"Requests per second: {requests_per_sec:.2f}")
#     print(f"Target: 300 req/sec, Actual: {requests_per_sec:.2f} req/sec")
    
#     # Show slowest requests
#     slow_requests = sorted(results, key=lambda x: x['time'], reverse=True)[:5]
#     print(f"\nTop 5 slowest requests:")
#     for req in slow_requests:
#         print(f"  Request {req['id']}: {req['time']:.3f}s - Status: {req['status']}")

# if __name__ == "__main__":
#     main()




import urllib.request
import urllib.error
import concurrent.futures
import time

def make_request(request_id):
    url = "http://localhost:8000/api/users/888"
    start_time = time.time()
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=10) as response:
            end_time = time.time()
            response_time = end_time - start_time
            status_code = response.getcode()
            return {
                'id': request_id,
                'status': status_code,
                'time': response_time,
                'success': status_code == 200
            }
    except urllib.error.HTTPError as e:
        end_time = time.time()
        return {
            'id': request_id,
            'status': e.code,
            'time': end_time - start_time,
            'success': False,
            'error': str(e)
        }
    except Exception as e:
        end_time = time.time()
        return {
            'id': request_id,
            'status': 'Error',
            'time': end_time - start_time,
            'success': False,
            'error': str(e)
        }

def main():
    total_requests = 100  # Fixed: Testing 100 requests
    print(f"Starting load test: {total_requests} requests")
    
    start_time = time.time()
    
    # Use ThreadPoolExecutor for concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        # Submit the actual number of requests
        futures = [executor.submit(make_request, i) for i in range(total_requests)]
        
        results = []
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    
    total_time = time.time() - start_time
    successful = sum(1 for r in results if r['success'])
    failed = total_requests - successful
    average_time = sum(r['time'] for r in results) / len(results) if results else 0
    requests_per_sec = total_requests / total_time
    
    print("\n=== RESULTS ===")
    print(f"Total requests: {total_requests}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total time: {total_time:.2f} seconds")
    print(f"Average response time: {average_time:.3f} seconds")
    print(f"Requests per second: {requests_per_sec:.2f}")
    
    # Show detailed error analysis
    if failed > 0:
        print(f"\n=== ERROR ANALYSIS ===")
        errors = {}
        for result in results:
            if not result['success']:
                error_key = f"Status {result['status']}" if result['status'] != 'Error' else result['error']
                errors[error_key] = errors.get(error_key, 0) + 1
        
        for error, count in errors.items():
            print(f"  {error}: {count} times")
    
    # Show slowest requests
    slow_requests = sorted(results, key=lambda x: x['time'], reverse=True)[:5]
    print(f"\nTop 5 slowest requests:")
    for req in slow_requests:
        error_info = f" - Error: {req.get('error', 'None')}" if not req['success'] else ""
        print(f"  Request {req['id']}: {req['time']:.3f}s - Status: {req['status']}{error_info}")

if __name__ == "__main__":
    main()
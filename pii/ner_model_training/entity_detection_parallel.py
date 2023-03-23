import multiprocessing
import subprocess


if __name__ == '__main__':
    job_ids = [0, 1, 2, 3]
    processes = []

    for job_id in job_ids:
        args = ['python', 'detect_entity.py', '--job_id', str(job_id)]
        process = multiprocessing.Process(target=subprocess.run, args=(args,))
        processes.append(process)
        process.start()

    for process in processes:
        process.join()

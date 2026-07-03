package ca.inn.bundler.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.*;

@Configuration
public class ExecutorConfig {
    @Bean(destroyMethod = "shutdown")
    // Note that ExecutorService extends Executor with more functionalities and thread pool control
    //Executors provides utility functions
    public ExecutorService bundleExecutor(
            @Value("${bundler.worker.threads:2}") int workerThreads,
             @Value("${bundler.worker.queue-capacity:100}") int queueCapacity
    ) {

        //return Executors.newFixedThreadPool(workerThreads); // This one does not control the queue size and it is unbounded which is not safe
        return new ThreadPoolExecutor(
                workerThreads, // Core worker count: how many bundle jobs can run at the same time.
                workerThreads, // Maximum worker count: same as core, so this is a fixed-size pool.
                0L, // Keep-alive time: not important here because core and max sizes are the same.
                TimeUnit.MILLISECONDS, // Unit for keep-alive time; not important for this fixed-size pool.
                new ArrayBlockingQueue<Runnable>(queueCapacity), // Bounded waiting queue for jobs when all workers are busy.
                new ThreadPoolExecutor.AbortPolicy() // Reject new jobs when workers and queue are full.
                );

        //Note: with a normal bounded queue like ArrayBlockingQueue, maximumPoolSize usually matters only after the queue is full.  new threads will be created
    }

    @Bean(destroyMethod = "shutdown")
    public ExecutorService bundleDownloadExecutor(
            @Value("${bundler.download.threads:8}") int downloadThreads
    ) {
        return Executors.newFixedThreadPool(downloadThreads);
    }

}

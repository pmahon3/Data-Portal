package ca.inn.bundler.support;

import java.util.Collections;
import java.util.List;
import java.util.concurrent.AbstractExecutorService;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;

// Test executor that simulates a full worker pool/queue by rejecting every task.
public class RejectingExecutorService extends AbstractExecutorService {

    private boolean shutdown;

    // ExecutorService.submit(...) delegates to execute(...), so throwing here tests submit rejection.
    @Override
    public void execute(Runnable command) {
        throw new RejectedExecutionException("test rejection");
    }

    @Override
    public void shutdown() {
        shutdown = true;
    }

    @Override
    public List<Runnable> shutdownNow() {
        shutdown = true;
        return Collections.emptyList();
    }

    @Override
    public boolean isShutdown() {
        return shutdown;
    }

    @Override
    public boolean isTerminated() {
        return shutdown;
    }

    @Override
    public boolean awaitTermination(long timeout, TimeUnit unit) {
        return shutdown;
    }
}

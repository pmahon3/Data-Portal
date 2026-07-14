package ca.inn.bundler.exception;

public class BundleNotReadyException extends RuntimeException {
    public BundleNotReadyException(String bundleId) {
        super("Bundle not ready:" + bundleId);;

    }

}

package ca.inn.bundler.exception;

import ca.inn.bundler.model.BundleStatus;

public class InvalidBundleStateTransitionException extends RuntimeException{
    public InvalidBundleStateTransitionException(BundleStatus currentStatus, BundleStatus nextStatus) {
        super("Invalid bundle status transition: " + currentStatus + " -> " + nextStatus);
    }
}

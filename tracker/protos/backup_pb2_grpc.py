# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc

from tracker.protos import backup_pb2 as backup__pb2


class GoogleDriveStub(object):
    """work with google drive through this service
    """

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.Backup = channel.unary_unary(
                '/backup.GoogleDrive/Backup',
                request_serializer=backup__pb2.DBRequest.SerializeToString,
                response_deserializer=backup__pb2.BackupReply.FromString,
                )
        self.DownloadLatestBackup = channel.unary_unary(
                '/backup.GoogleDrive/DownloadLatestBackup',
                request_serializer=backup__pb2.Empty.SerializeToString,
                response_deserializer=backup__pb2.DownloadReply.FromString,
                )
        self.Healthcheck = channel.unary_unary(
                '/backup.GoogleDrive/Healthcheck',
                request_serializer=backup__pb2.DBRequest.SerializeToString,
                response_deserializer=backup__pb2.HealthcheckReply.FromString,
                )


class GoogleDriveServicer(object):
    """work with google drive through this service
    """

    def Backup(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def DownloadLatestBackup(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def Healthcheck(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_GoogleDriveServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'Backup': grpc.unary_unary_rpc_method_handler(
                    servicer.Backup,
                    request_deserializer=backup__pb2.DBRequest.FromString,
                    response_serializer=backup__pb2.BackupReply.SerializeToString,
            ),
            'DownloadLatestBackup': grpc.unary_unary_rpc_method_handler(
                    servicer.DownloadLatestBackup,
                    request_deserializer=backup__pb2.Empty.FromString,
                    response_serializer=backup__pb2.DownloadReply.SerializeToString,
            ),
            'Healthcheck': grpc.unary_unary_rpc_method_handler(
                    servicer.Healthcheck,
                    request_deserializer=backup__pb2.DBRequest.FromString,
                    response_serializer=backup__pb2.HealthcheckReply.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'backup.GoogleDrive', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))


 # This class is part of an EXPERIMENTAL API.
class GoogleDrive(object):
    """work with google drive through this service
    """

    @staticmethod
    def Backup(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/backup.GoogleDrive/Backup',
            backup__pb2.DBRequest.SerializeToString,
            backup__pb2.BackupReply.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def DownloadLatestBackup(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/backup.GoogleDrive/DownloadLatestBackup',
            backup__pb2.Empty.SerializeToString,
            backup__pb2.DownloadReply.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def Healthcheck(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/backup.GoogleDrive/Healthcheck',
            backup__pb2.DBRequest.SerializeToString,
            backup__pb2.HealthcheckReply.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

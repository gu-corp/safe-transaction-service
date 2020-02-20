from typing import Optional

from django.contrib import admin
from django.db.models import F, Q
from django.db.models.functions import Greatest

from gnosis.eth import EthereumClientProvider

from .models import (EthereumBlock, EthereumEvent, EthereumTx, InternalTx,
                     InternalTxDecoded, MultisigConfirmation,
                     MultisigTransaction, ProxyFactory, SafeContract,
                     SafeMasterCopy, SafeStatus, WebHook)
from .services import IndexServiceProvider


@admin.register(EthereumBlock)
class EthereumBlockAdmin(admin.ModelAdmin):
    date_hierarchy = 'timestamp'
    list_display = ('number', 'timestamp', 'confirmed', 'gas_limit', 'gas_used', 'block_hash')
    list_filter = ('confirmed',)
    search_fields = ['=number', '=block_hash']
    ordering = ['-number']


class EthereumEventListFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'Event type'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'event_type'

    def lookups(self, request, model_admin):
        return (
            ('ERC20', 'ERC20 Transfer'),
            ('ERC721', 'ERC721 Transfer'),
            ('OTHER', 'Other events'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'ERC20':
            return queryset.erc20_events()
        elif self.value() == 'ERC721':
            return queryset.erc721_events()
        elif self.value() == 'OTHER':
            return queryset.not_erc_20_721_events()


@admin.register(EthereumEvent)
class EthereumEventAdmin(admin.ModelAdmin):
    list_display = ('ethereum_tx_id', 'log_index', 'erc20', 'erc721', 'address', 'from_', 'to', 'arguments')
    list_display_links = ('log_index', 'arguments')
    list_filter = (EthereumEventListFilter, )
    search_fields = ['arguments', 'address', '=ethereum_tx__tx_hash']
    raw_id_fields = ('ethereum_tx',)

    def from_(self, obj: EthereumEvent):
        return obj.arguments.get('from')

    def to(self, obj: EthereumEvent):
        return obj.arguments.get('to')

    def erc20(self, obj: EthereumEvent):
        return obj.is_erc20()

    def erc721(self, obj: EthereumEvent):
        return obj.is_erc721()

    # Fancy icons
    erc20.boolean = True
    erc721.boolean = True


@admin.register(EthereumTx)
class EthereumTxAdmin(admin.ModelAdmin):
    list_display = ('block_id', 'tx_hash', 'nonce', '_from', 'to')
    search_fields = ['=tx_hash', '=_from', '=to']
    ordering = ['-block_id']
    raw_id_fields = ('block',)


@admin.register(InternalTx)
class InternalTxAdmin(admin.ModelAdmin):
    list_display = ('ethereum_tx_id', 'block_number', '_from', 'to', 'value', 'call_type', 'trace_address')
    list_filter = ('tx_type', 'call_type')
    list_select_related = ('ethereum_tx',)
    ordering = ['-ethereum_tx__block_id',
                '-ethereum_tx__transaction_index',
                '-trace_address']
    raw_id_fields = ('ethereum_tx',)
    search_fields = ['=ethereum_tx__block__number', '=_from', '=to', '=ethereum_tx__tx_hash']


class InternalTxDecodedListFilter(admin.SimpleListFilter):
    title = 'Gnosis official Safes'
    parameter_name = 'official_safes'

    def lookups(self, request, model_admin):
        return (
            ('YES', 'Yes'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'YES':
            return queryset.filter(
                Q(internal_tx___from__in=SafeContract.objects.values('address'))  # Just Safes indexed
                | Q(function_name='setup')  # This way we can index new Safes without events
            )


@admin.register(InternalTxDecoded)
class InternalTxDecodedAdmin(admin.ModelAdmin):
    actions = ['process_again']
    list_display = ('block_number', 'processed', 'internal_tx_id', 'tx_hash', 'address', 'function_name', 'arguments')
    list_filter = ('function_name', 'processed', InternalTxDecodedListFilter)
    list_select_related = ('internal_tx__ethereum_tx',)
    ordering = ['-internal_tx__ethereum_tx__block_id',
                '-internal_tx__ethereum_tx__transaction_index',
                '-internal_tx__trace_address']
    raw_id_fields = ('internal_tx',)
    search_fields = ['function_name', 'arguments', '=internal_tx__to', '=internal_tx___from',
                     '=internal_tx__ethereum_tx__tx_hash']

    def process_again(self, request, queryset):
        queryset.filter(processed=True).update(processed=False)
    process_again.short_description = "Process internal tx again"


class MultisigConfirmationListFilter(admin.SimpleListFilter):
    title = 'Has multisig transaction'
    parameter_name = 'has_multisig_tx'

    def lookups(self, request, model_admin):
        return (
            ('YES', 'Yes'),
            ('NO', 'No'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'YES':
            return queryset.exclude(multisig_transaction=None)
        elif self.value() == 'NO':
            return queryset.filter(multisig_transaction=None)


@admin.register(MultisigConfirmation)
class MultisigConfirmationAdmin(admin.ModelAdmin):
    list_display = ('block_number', 'multisig_transaction_hash', 'has_multisig_tx', 'ethereum_tx_id', 'owner')
    list_filter = (MultisigConfirmationListFilter, )
    list_select_related = ('ethereum_tx',)
    raw_id_fields = ('ethereum_tx', 'multisig_transaction')
    search_fields = ['=multisig_transaction__safe', '=ethereum_tx__tx_hash', '=multisig_transaction_hash', '=owner']

    def has_multisig_tx(self, obj: MultisigConfirmation) -> bool:
        return bool(obj.multisig_transaction_id)
    has_multisig_tx.boolean = True

    def block_number(self, obj: MultisigConfirmation) -> Optional[int]:
        if obj.ethereum_tx:
            return obj.ethereum_tx.block_id


@admin.register(MultisigTransaction)
class MultisigTransactionAdmin(admin.ModelAdmin):
    date_hierarchy = 'created'
    list_display = ('created', 'safe', 'executed', 'successful', 'safe_tx_hash', 'ethereum_tx_id', 'to', 'value',
                    'nonce', 'data')
    list_filter = ('failed', )
    list_select_related = ('ethereum_tx',)
    ordering = ['-created']
    raw_id_fields = ('ethereum_tx',)
    search_fields = ['=ethereum_tx__tx_hash', '=safe', 'to']

    def executed(self, obj: MultisigTransaction):
        return obj.executed
    executed.boolean = True

    def successful(self, obj: MultisigTransaction):
        return not obj.failed
    successful.boolean = True


class MonitoredAddressAdmin(admin.ModelAdmin):
    actions = ['reindex', 'reindex_last_day', 'reindex_last_month']
    list_display = ('address', 'initial_block_number', 'tx_block_number')
    search_fields = ['address']

    def has_delete_permission(self, request, obj=None):
        return False

    def reindex(self, request, queryset):
        queryset.update(tx_block_number=F('initial_block_number'))
    reindex.short_description = "Reindex from initial block"

    def reindex_last_day(self, request, queryset):
        queryset.update(tx_block_number=Greatest(F('tx_block_number') - 6000, 0))
    reindex_last_day.short_description = "Reindex last 24 hours"

    def reindex_last_month(self, request, queryset):
        queryset.update(tx_block_number=Greatest(F('tx_block_number') - 200000, 0))
    reindex_last_month.short_description = "Reindex last month"


@admin.register(SafeMasterCopy)
class SafeMasterCopyAdmin(MonitoredAddressAdmin):
    pass


@admin.register(ProxyFactory)
class ProxyFactoryAdmin(MonitoredAddressAdmin):
    pass


class SafeContractERC20ListFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'ERC20 Indexation'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'erc20_indexation'

    def lookups(self, request, model_admin):
        return (
            ('YES', 'ERC20 Indexation updated'),
            ('NO', 'ERC20 Indexation not updated'),
        )

    def queryset(self, request, queryset):
        current_block_number = EthereumClientProvider().current_block_number
        condition = {'erc20_block_number__gte': current_block_number - 200}
        if self.value() == 'YES':
            return queryset.filter(**condition)
        elif self.value() == 'NO':
            return queryset.exclude(**condition)


@admin.register(SafeContract)
class SafeContractAdmin(admin.ModelAdmin):
    actions = ['reindex', 'reindex_last_day', 'reindex_last_month']
    list_display = ('created_block_number', 'address', 'ethereum_tx_id', 'erc20_block_number')
    list_filter = (SafeContractERC20ListFilter, )
    list_select_related = ('ethereum_tx',)
    ordering = ['-ethereum_tx__block_id']
    raw_id_fields = ('ethereum_tx',)
    search_fields = ['address']

    def reindex(self, request, queryset):
        queryset.exclude(
            ethereum_tx=None
        ).update(erc20_block_number=F('ethereum_tx__block_id'))
    reindex.short_description = "Reindex from initial block"

    def reindex_last_day(self, request, queryset):
        queryset.update(erc20_block_number=Greatest(F('erc20_block_number') - 6000, 0))
    reindex_last_day.short_description = "Reindex last 24 hours"

    def reindex_last_month(self, request, queryset):
        queryset.update(erc20_block_number=Greatest(F('erc20_block_number') - 200000, 0))
    reindex_last_month.short_description = "Reindex last month"


@admin.register(SafeStatus)
class SafeStatusAdmin(admin.ModelAdmin):
    actions = ['remove_and_index']
    list_display = ('block_number', 'internal_tx_id', 'address', 'owners', 'threshold', 'nonce', 'master_copy')
    list_filter = ('threshold', 'master_copy')
    list_select_related = ('internal_tx__ethereum_tx',)
    ordering = ['-internal_tx__ethereum_tx__block_id', '-internal_tx_id']
    raw_id_fields = ('internal_tx',)
    search_fields = ['address', 'owners', '=internal_tx__ethereum_tx__tx_hash']

    def has_delete_permission(self, request, obj=None):
        return False

    def remove_and_index(self, request, queryset):
        safe_addresses = queryset.distinct().values('address')
        IndexServiceProvider().reindex_addresses(safe_addresses)
    remove_and_index.short_description = "Remove and index again"


@admin.register(WebHook)
class WebHookAdmin(admin.ModelAdmin):
    list_display = ('address', 'url', 'pending_outgoing_transaction', 'new_confirmation',
                    'new_executed_outgoing_transaction', 'new_incoming_transaction')
    list_filter = ('pending_outgoing_transaction', 'new_confirmation', 'new_executed_outgoing_transaction',
                   'new_incoming_transaction')
    ordering = ['-pk']
    search_fields = ['address', 'url']
